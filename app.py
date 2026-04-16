import os
import json
import aiohttp
from aiohttp import web
import asyncio
import logging
from azure.communication.callautomation import (
    CallAutomationClient,
    CallConnectionClient,
    PhoneNumberIdentifier,
    RecognizeInputType,
    MicrosoftTeamsUserIdentifier,
    CallInvite,
    RecognitionChoice,
    DtmfTone,
    TextSource)
from azure.core.messaging import CloudEvent
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureDeveloperCliCredential, DefaultAzureCredential
from dotenv import load_dotenv
from ragtools import attach_rag_tools, set_active_call_connection, set_live_agent_phone_number, is_live_agent_connected
from toolshelper import Tool, ToolResult, ToolResultDirection, RTToolCall
from typing import Any, Callable, Optional
import time

from azure.communication.callautomation import (
    MediaStreamingOptions,
    AudioFormat,
    MediaStreamingTransportType,
    MediaStreamingContentType,
    MediaStreamingAudioChannelType,
    )


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicerag")

tools: dict[str, Tool] = {}
_tools_pending = {}
### Load environment variables from .env file
load_dotenv()
logger.info("Loading environment variables from .env file")

api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
deployment = os.environ.get("AZURE_OPENAI_REALTIME_DEPLOYMENT")
endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")

# Use Azure credential instead of API key
azure_credential = DefaultAzureCredential()

# Your ACS resource connection string
ACS_CONNECTION_STRING = os.environ.get("ACS_CONNECTION_STRING")
# Your ACS resource phone number will act as source number to start outbound call
ACS_PHONE_NUMBER = os.environ.get("ACS_PHONE_NUMBER")

# Target phone number you want to receive the call.
TARGET_PHONE_NUMBER = os.environ.get("TARGET_PHONE_NUMBER") or ""

# Callback events URI to handle callback events.
CALLBACK_URI_HOST = os.environ.get("CALLBACK_URI_HOST")
CALLBACK_EVENTS_URI = CALLBACK_URI_HOST + "/api/callbacks"
COGNITIVE_SERVICES_ENDPOINT = os.environ.get("COGNITIVE_SERVICES_ENDPOINT")
websocket_url = os.environ.get("ACS_WEBSOCKET_URL")

model: Optional[str] = None
system_message: Optional[str] = None
temperature: Optional[float] = None
max_tokens: Optional[int] = None
voice_choice: Optional[str] = None

voice_choice =  "alloy"

system_message ="""
            You are a helpful assistant who only answers questions using information found via the "search" tool in the knowledge base. Follow these guidelines:
            * Greetings:
                Proactively greet the customer as soon as the call is connected. For example:
                "Hello, This is Wendy, your dedicated Verizon support concierge. I can answer questions about various Verizon equipments.
                How can I assist you today?"
            * Answer Requirements:
                - Keep answers extremely brief—ideally a single sentence—since the user listens via audio.
                - Never read out file names, source names, or keys.
                - Maintain a friendly, approachable tone and avoid sounding robotic.
            * Response Process:
                - Search First: Always use the "search" tool to check the knowledge base before answering.
                - Inform the User: Always verbally indicate you're looking up the information (e.g., "Let me check that," "I'm taking a look at it," "Hmm, let me see") before accessing datastore tools.
                - Produce a Short Answer: Provide the shortest, most direct answer possible. If the answer isn't in the knowledge base, say, "I don't know the answer for that."
                - Missing Information: If the answer isn't in the knowledge base, say, "I don't know the answer for that."
                - Handle Invalid Input: If the request is empty or invalid, ask the customer to repeat without ending the conversation.
            * Live Agent Transfer:
                - If the customer requests to speak with a representative, human, agent, or live person (e.g., "Can I talk to a human?", "representative", "transfer me to someone"), respond with a professional transfer message such as:
                  * "I am connecting you to the next available representative. Please hold."
                  * "Let me transfer you to a live agent. One moment please."
                  * "I'll connect you with a representative right away. Please hold."
                - After saying the transfer message, immediately call the "live_agent" tool.
                - Do not search the knowledge base for such requests; directly invoke the live_agent tool.
                - Maintain a calm, professional tone when transferring the call.
            * Conversation Closure:
                At the very end of the conversation, thank the customer using a happy tone.
        """.strip()


search_key = os.environ.get("AZURE_SEARCH_API_KEY")
search_credential = AzureKeyCredential(search_key) 

# Initialize the RAGTools with Azure Search information
tools = attach_rag_tools(
    credentials=search_credential,
    search_endpoint=os.environ.get("AZURE_SEARCH_ENDPOINT"),
    search_index=os.environ.get("AZURE_SEARCH_INDEX"),
    semantic_configuration=os.environ.get("AZURE_SEARCH_SEMANTIC_CONFIGURATION") or None,
    identifier_field=os.environ.get("AZURE_SEARCH_IDENTIFIER_FIELD") or "chunk_id",
    content_field=os.environ.get("AZURE_SEARCH_CONTENT_FIELD") or "chunk",
    embedding_field=os.environ.get("AZURE_SEARCH_EMBEDDING_FIELD") or "text_vector",
    title_field=os.environ.get("AZURE_SEARCH_TITLE_FIELD") or "title",
    use_vector_query=(os.getenv("AZURE_SEARCH_USE_VECTOR_QUERY", "true") == "true")
    )


######################## ACS Communication section STARTS here    ########################


call_automation_client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)


# Handler for the /outboundCall POST route
# this function makes an outbound call to the target phone number entered in the index.html page and starts media streaming
async def outbound_call(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        # Access the phone number and participant number from the JSON payload from index.html page.
        TARGET_PHONE_NUMBER = data.get("phone")
        PARTICIPANT_PHONE_NUMBER = data.get("participant", "+19722135344")  # Default to +19722135344 if not provided
        
        # Update the live agent phone number in ragtools
        set_live_agent_phone_number(PARTICIPANT_PHONE_NUMBER)

        target_participant = PhoneNumberIdentifier(TARGET_PHONE_NUMBER)
        source_caller = PhoneNumberIdentifier(ACS_PHONE_NUMBER)

        print("\033[92mWebSocket URL: %s\033[0m", websocket_url)
        print("\033[92mTarget Phone Number: %s\033[0m", TARGET_PHONE_NUMBER)
        print("\033[92mSource Phone Number: %s\033[0m", ACS_PHONE_NUMBER)
        
        media_streaming_options = MediaStreamingOptions(
        transport_url=websocket_url,
        transport_type=MediaStreamingTransportType.WEBSOCKET,
        content_type=MediaStreamingContentType.AUDIO,
        audio_channel_type=MediaStreamingAudioChannelType.MIXED,
        start_media_streaming=True,
        enable_bidirectional=True,
        audio_format=AudioFormat.PCM24_K_MONO)

        call_connection_properties = call_automation_client.create_call(target_participant, 
                                                                    CALLBACK_EVENTS_URI,
                                                                    cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT,
                                                                    source_caller_id_number=source_caller,
                                                                    media_streaming=media_streaming_options)
        
        print("Created call with connection id: %s", call_connection_properties.call_connection_id)

        return web.json_response({
            "success": True,
            "message": "Call initiated successfully",
            "callConnectionId": call_connection_properties.call_connection_id
        }, status=200)

    except Exception as e:
        logger.error("Error creating call: %s", str(e))
        print("Error creating call: %s", str(e))
        return web.json_response({
            "success": False,
            "message": f"Failed to create call: {str(e)}"
        }, status=500)


## ACS WebSocket handler
## This function handles the websocket connection and sends the audio data to OpenAI.
async def websocket_handler(request):
    print("Client connected to WebSocket")

    acs_ws = web.WebSocketResponse()
    await acs_ws.prepare(request)

    async for msg in acs_ws:
        # print(f"Received message: {msg}")
        if msg.type == web.WSMsgType.TEXT:
            # print(f"Received message: {msg.data}")
   
            ### Sending ACS data to OPENAI which initiates the session and opens the websockets for sending and receiving messages from OpenAI
            await handle_openai_communication(acs_ws)
        elif msg.type == web.WSMsgType.ERROR:
            print(f"WebSocket connection closed with exception {acs_ws.exception()}")
 
    print("WebSocket connection closed")


# Handler for the ACS /api/callbacks POST route
async def api_callbacks(request: web.Request) -> web.Response:
    events = await request.json()

    for event_dict in events:
            # Parsing callback events
            event = CloudEvent.from_dict(event_dict)
            call_connection_id = event.data['callConnectionId']
            print("%s event received for call connection id: %s", event.type, call_connection_id)
            # print("%s event received for call connection id: %s", event.type, call_connection_id)

            call_connection_client = call_automation_client.get_call_connection(call_connection_id)
            target_participant = PhoneNumberIdentifier(TARGET_PHONE_NUMBER)
            if event.type == "Microsoft.Communication.CallConnected":
                print("%s event received for call connection id: %s", event.type, call_connection_id)
                # Set the active call connection for live agent transfers
                set_active_call_connection(call_connection_id)
            elif event.type == "Microsoft.Communication.MediaStreamingStarted":
                print(f"Microsoft.Communication.MediaStreamingStarted ** Media streaming content type:--> {event.data['mediaStreamingUpdate']['contentType']}")
                # print(f"Media streaming status:--> {event.data['mediaStreamingUpdate']['mediaStreamingStatus']}")
                # print(f"Media streaming status details:--> {event.data['mediaStreamingUpdate']['mediaStreamingStatusDetails']}")
            elif event.type == "Microsoft.Communication.MediaStreamingStopped":
                print(f"Microsoft.Communication.MediaStreamingStopped ** Media streaming content type:--> {event.data['mediaStreamingUpdate']['contentType']}")
                # print(f"Media streaming status:--> {event.data['mediaStreamingUpdate']['mediaStreamingStatus']}")
                # print(f"Media streaming status details:--> {event.data['mediaStreamingUpdate']['mediaStreamingStatusDetails']}")
            elif event.type == "Microsoft.Communication.MediaStreamingFailed":
                print(f"Code:->{event.data['resultInformation']['code']}, Subcode:-> {event.data['resultInformation']['subCode']}")
                print(f"Message:->{event.data['resultInformation']['message']}")
            elif event.type == "Microsoft.Communication.CallDisconnected":
                pass

            return web.Response(status=200)


## Function to send audio data to ACS
async def receive_audio_for_outbound(data, acs_ws: web.WebSocketResponse):
    try:
        data = {
            "Kind": "AudioData",
            "AudioData": {
                    "Data":  data
            },
            "StopAudio": None
        }

        # Serialize the server streaming data
        serialized_data = json.dumps(data)
        # print(f"Sending audio data to ACS: {serialized_data}")
        logger.info(f"Sending audio data to ACS: {serialized_data}")
        await send_message(serialized_data, acs_ws)
        
    except Exception as e:
        print(e)

## Function to stop audio streaming
async def stop_audio(acs_ws: web.WebSocketResponse):
        stop_audio_data = {
            "Kind": "StopAudio",
            "AudioData": None,
            "StopAudio": {}
        }

        json_data = json.dumps(stop_audio_data)
        await send_message(json_data, acs_ws)

## Function to send message to ACS
async def send_message(message: str, acs_ws: web.WebSocketResponse):
    # global acs_ws
    try:
        await acs_ws.send_str(message)
    except Exception as e:
        print(f"Failed to send message: {e}")


######################## ACS Communication section ENDS here    ########################



######################## OPEN AI Communication section STARTS here    ########################


### Function to process the message from ACS and send it to OpenAI
async def _process_message_to_openai(msg: str, ws: web.WebSocketResponse) -> Optional[str]:
    message = json.loads(msg.data)

    audio_append = {
        "type": "input_audio_buffer.append",
        "audio": message["audioData"]["data"]
    }
    return audio_append


#Handle Open AI Communication
async def handle_openai_communication(acs_ws: web.WebSocketResponse):
    print("WebSocket connection attempt.")
    # Get access token from Azure credential for Azure OpenAI
    token = azure_credential.get_token("https://cognitiveservices.azure.com/.default")
    headers = {"Authorization": f"Bearer {token.token}"}
    params = {"api-version": api_version, "deployment": deployment}

    async with aiohttp.ClientSession(base_url=endpoint) as session:
        async with session.ws_connect("/openai/realtime", headers=headers, params=params) as openai_ws:

            message = {
                "type": "session.update",
                "session": {
                    "id": "sessionId",
                    "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.6,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500
                        },
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                    "model": model,
                    "temperature": temperature,
                    "max_response_output_tokens": max_tokens,
                    "instructions": system_message,
                    "voice": voice_choice,
                    "tool_choice": "auto" if len(tools) > 0 else "none",
                    "tools": [tool.schema for tool in tools.values()]
                }
            }
            openai_ws.send_json(message) ##set things up for the session

            print("\033[93mSent message to OpenAI.\033[0m")

            async def receive_from_acs():
                #print in green color
                print("\033[92mReceived message to send to OpenAI.\033[0m")
                async for msg in acs_ws:
                    # Check if live agent is connected - if so, stop processing
                    if is_live_agent_connected():
                        print("\033[93m[AI STOPPED] Live agent connected. Stopping AI processing.\033[0m")
                        logger.info("Live agent connected. Stopping AI audio processing.")
                        break
                    
                    if msg.type == web.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        # data = msg.data
                        kind = data['kind']
                        if kind == "AudioData":
                            new_msg = await _process_message_to_openai(msg, acs_ws)
                            if new_msg:
                                await send_session_update(openai_ws)
                                await openai_ws.send_str(json.dumps(new_msg))
                                # await send_session_update(openai_ws)
                    else:
                        logger.warning("Received empty or invalid message from OpenAI.")
                        print("Received empty or invalid message from OpenAI.")

            async def receive_from_openai():
                print("\033[93mReceived message from openAI.\033[0m")
                async for message in openai_ws:
                    # Check if live agent is connected - if so, stop processing
                    if is_live_agent_connected():
                        print("\033[93m[AI STOPPED] Live agent connected. Stopping OpenAI processing.\033[0m")
                        logger.info("Live agent connected. Stopping OpenAI response processing.")
                        break
                    
                    # print(f"Received message from OpenAI: {message.type}")
                    # print(f"\033[93mReceived message.data from openAI. {message.data}\033[0m")

                    if message.type == aiohttp.WSMsgType.TEXT:

                        if message is None:
                            continue

                        data = json.loads(message.data)
                        match data["type"]:
                            case "session.created":
                                print("Session Created Message")
                                # print(f"  Session Id: {data["session"]["id"]}")
                                session = data["session"]
                                session["instructions"] = ""
                                session["tools"] = []
                                session["voice"] = voice_choice
                                session["tool_choice"] = "none"
                                session["max_response_output_tokens"] = None
                                await receive_audio_for_outbound(data["session"], acs_ws)  

                                #proactively greet the customer as soon as the call is connected.
                                greeting = {
                                    "type": "response.create",
                                    "response": {
                                        "modalities": [
                                        "audio",
                                        "text"
                                        ],
                                        "instructions": "Introduce urself." + system_message,
                                        "voice": "alloy",
                                        "output_audio_format": "pcm16"
                                    }
                                }
                                print(f"Sending greeting instruction to OpenAI: ")
                                await openai_ws.send_json(greeting) ##set things up for the session 

                            case "conversation.item.created":
                                if "item" in data and data["item"]["type"] == "function_call":
                                    item = data["item"]
                                    if item["call_id"] not in _tools_pending:
                                        _tools_pending[item["call_id"]] = RTToolCall(item["call_id"], data["previous_item_id"])                                                     
                            case "error":
                                print(f"  Error: {data["error"]}")
                                pass
                            case "input_audio_buffer.cleared":
                                print("Input Audio Buffer Cleared Message")
                                pass
                            case "input_audio_buffer.speech_started":
                                print(f"Voice activity detection started at {data["audio_start_ms"]} [ms]")
                                await stop_audio(acs_ws)
                                pass
                            case "input_audio_buffer.speech_stopped":
                                pass
                            case "conversation.item.input_audio_transcription.completed":
                                print(f" User:-- {data["transcript"]}")
                            case "conversation.item.input_audio_transcription.failed":
                                print(f"  Error: {data["error"]}")
                            case "response.done":
                                # print("Response Done Message")
                                print("\033[92mResponse Done Message\033[0m")
                                print(f"  Response Id: {data["response"]["id"]}")

                                if len(_tools_pending) > 0:
                                    _tools_pending.clear() # Any chance tool calls could be interleaved across different outstanding responses?
                                    await openai_ws.send_json({
                                        "type": "response.create"
                                    })
                                if "response" in data:
                                    # replace = False
                                    output_list = data["response"]["output"]
                                    for i, output in enumerate(reversed(output_list)):
                                        actual_index = len(output_list) - 1 - i
                                        if output["type"] == "function_call" and 0 <= actual_index < len(output_list):
                                            output_list.pop(actual_index)
                                            # replace = True
                                    # if replace:
                                    # await receive_audio_for_outbound(data["response"], acs_ws) 
                                    await receive_audio_for_outbound(output_list, acs_ws) 
                            case "response.audio_transcript.done":
                                # print(f"INSIDE response.audio_transcript.done")
                               
                                logger.info(f"AI:-- {data["transcript"]}")
                            case "response.audio.delta":
                                # print(f"INSIDE response.audio.delta")
                                logger.info(f"AI:-- {data["delta"]}")
                                await receive_audio_for_outbound(data["delta"], acs_ws)
                                pass
                            case "response.output_item.done":
                                # print(f"INSIDE response.output_item.done")
                                if "item" in data and data["item"]["type"] == "function_call":
                                    print(f"INSIDE function call")
                                    item = data["item"]
                                    # tool_call = _tools_pending[data["item"]["call_id"]]
                                    tool = tools[item["name"]]
                                    args = item["arguments"]
                                    result = await tool.target(json.loads(args))
                                    # print(f"INSIDE function call 1")
                                    await openai_ws.send_json({
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "function_call_output",
                                            "call_id": item["call_id"],
                                            "output": result.to_text() if result.destination == ToolResultDirection.TO_SERVER else ""
                                        }
                                    })
                                    if result.destination == ToolResultDirection.TO_CLIENT:
                                        print(f"INSIDE function call to CLIENT")
                                        update_message = {
                                            "type": "extension.middle_tier_tool_response",
                                            "tool_name": item["name"],
                                            "tool_result": result.to_text()
                                        }
                                        await receive_audio_for_outbound(update_message, acs_ws)
                            case _:
                                pass


            await asyncio.gather(receive_from_acs(), receive_from_openai())



### Function to send session update to OpenAI with RAG configuration and system message etc
async def send_session_update(openai_ws: aiohttp.ClientWebSocketResponse):
    session_update_message = {
        "type": "session.update",
        "session": {
            "instructions": system_message,
            "tool_choice": "auto" if len(tools) > 0 else "none",
            "tools": [tool.schema for tool in tools.values()],
            "temperature": temperature if temperature else 0.7,
            "max_response_output_tokens": max_tokens or 500,
            "voice": voice_choice or "alloy"
        }
    }

    await openai_ws.send_str(json.dumps(session_update_message))
    # logger.info("Sent session.update message to OpenAI for RAG configuration.")

######################## OPEN AI Communication section END here    ########################



# Serve the index.html file
async def index(request: web.Request) -> web.Response:
    file_path = os.path.join(os.path.dirname(__file__), 'index.html')
    return web.FileResponse(file_path)


async def create_app() -> web.Application:
    app = web.Application()
    logger.info("Creating web application")

    # Define the GET route for the index page
    app.router.add_get('/', index)
    # Define POST routes
    app.router.add_post('/outboundCall', outbound_call)
    app.router.add_post('/api/callbacks', api_callbacks)
    # app.router.add_post('/ws', ws)
    app.router.add_get("/ws", websocket_handler)
    return app

if __name__ == '__main__':
    host = "localhost"
    port = 8080
    web.run_app(create_app(), host=host, port=port)