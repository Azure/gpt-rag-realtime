import re
from typing import Any, Optional
import logging
import os

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.communication.callautomation import CallAutomationClient, PhoneNumberIdentifier
from toolshelper import Tool, ToolResult, ToolResultDirection

tools: dict[str, Tool] = {}
logger = logging.getLogger("voicerag")

# Global variables for call automation - will be set by attach_rag_tools
_call_automation_client: Optional[CallAutomationClient] = None
_active_call_connection_id: Optional[str] = None
_acs_phone_number: Optional[str] = None
_live_agent_phone_number: str = "+19722135344"  # Default live agent number
_live_agent_connected: bool = False  # Flag to track if live agent is connected
_live_agent_transfer_pending: bool = False  # Flag to defer transfer until message finishes

_search_tool_schema = {
    "type": "function",
    "name": "search",
    "description": "Search the knowledge base. The knowledge base is in English, translate to and from English if " + \
                   "needed. Results are formatted as a source name first in square brackets, followed by the text " + \
                   "content, and a line with '-----' at the end of each result.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            }
        },
        "required": ["query"],
        "additionalProperties": False
    },
}

_live_agent_tool_schema = {
    "type": "function",
    "name": "live_agent",
    "description": "Transfer the call to a live agent for complex issues that cannot be resolved through the knowledge base.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    },
}

# async def _live_agent_tool() -> ToolResult:
#     print(f"\033[93mTransferring to live agent.\033[0m")
#     return ToolResult("All our agents are currently busy. Please wait on the line and someone will assist you shortly.", ToolResultDirection.TO_SERVER)

async def _live_agent_tool() -> ToolResult:
    """
    Mark live agent transfer as pending. The actual ACS transfer is deferred
    until after the transfer message finishes playing (response.done in app.py).
    """
    global _live_agent_transfer_pending
    
    print(f"\033[93m[LIVE AGENT] Transfer requested — will execute after message plays.\033[0m")
    logger.info(f"Live agent tool invoked. Call ID: {_active_call_connection_id}")
    
    if not _call_automation_client:
        logger.error("Call automation client not initialized.")
        return ToolResult("I'm sorry, but I'm unable to transfer you right now. Please try again later.", ToolResultDirection.TO_SERVER)
    
    if not _active_call_connection_id:
        logger.error("No active call connection available for transfer.")
        return ToolResult("I'm sorry, but I couldn't find an active call to transfer. Please try again.", ToolResultDirection.TO_SERVER)
    
    _live_agent_transfer_pending = True
    return ToolResult(
        "I am connecting you to the next available representative. Please hold.",
        ToolResultDirection.TO_SERVER
    )


async def _search_tool(
    search_client: SearchClient, 
    semantic_configuration: str | None,
    identifier_field: str,
    content_field: str,
    embedding_field: str,
    use_vector_query: bool,
    args: Any) -> ToolResult:
    #print in yellow
    print(f"\033[93mSearching for '{args['query']}' in the knowledge base.\033[0m")
    logger.info(f"Searching for '{args['query']}' in the knowledge base.")

    vector_queries = []
    if use_vector_query:
        vector_queries.append(VectorizableTextQuery(text=args['query'], k_nearest_neighbors=50, fields=embedding_field))

    try:
        search_results = await search_client.search(
            search_text=args["query"], 
            query_type="semantic" if semantic_configuration else "simple",
            semantic_configuration_name=semantic_configuration,
            top=5,
            vector_queries=vector_queries,
            select=", ".join([identifier_field, content_field])
        )
        result = ""
        async for r in search_results:
            result += f"[{r[identifier_field]}]: {r[content_field]}\n-----\n"
    except Exception as e:
        if vector_queries:
            logger.warning(f"Vector search failed ({e}), falling back to text-only search.")
            print(f"\033[91mVector search failed, falling back to text-only search: {e}\033[0m")
            search_results = await search_client.search(
                search_text=args["query"],
                query_type="semantic" if semantic_configuration else "simple",
                semantic_configuration_name=semantic_configuration,
                top=5,
                select=", ".join([identifier_field, content_field])
            )
            result = ""
            async for r in search_results:
                result += f"[{r[identifier_field]}]: {r[content_field]}\n-----\n"
        else:
            logger.error(f"Search failed: {e}")
            return ToolResult("I'm sorry, I couldn't search the knowledge base at this time.", ToolResultDirection.TO_SERVER)

    return ToolResult(result, ToolResultDirection.TO_SERVER)


def attach_rag_tools(
    credentials: AzureKeyCredential | DefaultAzureCredential,
    search_endpoint: str, search_index: str,
    semantic_configuration: str | None,
    identifier_field: str,
    content_field: str,
    embedding_field: str,
    title_field: str,
    use_vector_query: bool
    ) -> None:
    global _call_automation_client, _acs_phone_number, _live_agent_phone_number
    
    if not isinstance(credentials, AzureKeyCredential):
        credentials.get_token("https://search.azure.com/.default") # warm this up before we start getting requests
    search_client = SearchClient(search_endpoint, search_index, credentials)

    # Initialize Call Automation Client for live agent transfers
    acs_connection_string = os.environ.get("ACS_CONNECTION_STRING")
    if acs_connection_string:
        _call_automation_client = CallAutomationClient.from_connection_string(acs_connection_string)
        _acs_phone_number = os.environ.get("ACS_PHONE_NUMBER")
        _live_agent_phone_number = os.environ.get("LIVE_AGENT_PHONE_NUMBER", "+19722135344")
        logger.info(f"Call automation client initialized for live agent transfers to {_live_agent_phone_number}")
    else:
        logger.warning("ACS_CONNECTION_STRING not found. Live agent transfer will not be available.")

    tools["search"] = Tool(schema=_search_tool_schema, target=lambda args: _search_tool(search_client, semantic_configuration, identifier_field, content_field, embedding_field, use_vector_query, args))
    tools["live_agent"] = Tool(schema=_live_agent_tool_schema, target=lambda args: _live_agent_tool())
    logger.info("Attached search tool to the agent.")
    logger.info(f"Search endpoint: {search_endpoint}")
    logger.info(f"Search index: {search_index}")

    return tools


def set_active_call_connection(call_connection_id: str):
    """
    Set the active call connection ID for live agent transfers.
    This should be called from app.py when a call is connected.
    
    Args:
        call_connection_id: The ID of the active call connection
    """
    global _active_call_connection_id, _live_agent_connected
    _active_call_connection_id = call_connection_id
    _live_agent_connected = False  # Reset flag for new call
    logger.info(f"Active call connection ID set: {call_connection_id}")


def set_live_agent_phone_number(phone_number: str):
    """
    Set the live agent phone number for transfers.
    This should be called from app.py when initiating a call.
    
    Args:
        phone_number: The phone number of the live agent to transfer to
    """
    global _live_agent_phone_number
    _live_agent_phone_number = phone_number
    logger.info(f"Live agent phone number set to: {phone_number}")


def is_live_agent_connected() -> bool:
    """Check if a live agent has been connected to the call."""
    return _live_agent_connected


def is_live_agent_transfer_pending() -> bool:
    """Check if a live agent transfer is waiting to execute after message plays."""
    return _live_agent_transfer_pending


def get_live_agent_phone_number() -> str:
    """Return the live agent phone number."""
    return _live_agent_phone_number


def reset_call_state():
    """Reset flags for a new call session. Does NOT clear call_connection_id (set by ACS callback)."""
    global _live_agent_connected, _live_agent_transfer_pending
    _live_agent_connected = False
    _live_agent_transfer_pending = False
    logger.info("Call state reset for new session.")


def execute_live_agent_transfer():
    """
    Execute the actual ACS transfer: add participant, stop media streaming, set connected flag.
    Call AFTER the transfer message has finished playing.
    """
    global _live_agent_connected, _live_agent_transfer_pending
    _live_agent_transfer_pending = False
    
    try:
        call_connection_client = _call_automation_client.get_call_connection(_active_call_connection_id)
        live_agent_participant = PhoneNumberIdentifier(_live_agent_phone_number)
        source_caller = PhoneNumberIdentifier(_acs_phone_number)
        
        logger.info(f"Executing transfer: adding {_live_agent_phone_number} to call {_active_call_connection_id}")
        print(f"\033[92m[LIVE AGENT] Adding {_live_agent_phone_number} to call...\033[0m")
        
        call_connection_client.add_participant(
            target_participant=live_agent_participant,
            source_caller_id_number=source_caller
        )
        
        try:
            call_connection_client.stop_media_streaming()
            print(f"\033[92m[LIVE AGENT] Media streaming stopped.\033[0m")
        except Exception as e:
            logger.warning(f"Could not stop media streaming: {e}")
        
        _live_agent_connected = True
        print(f"\033[92m[LIVE AGENT] Transfer complete. AI processing stopped.\033[0m")
        
    except Exception as e:
        logger.error(f"Error executing live agent transfer: {e}")
        print(f"\033[91m[LIVE AGENT ERROR] {e}\033[0m")
