import os
import logging
import httpx
from typing import Dict

ORCHESTRATOR_BASE_URL = os.environ.get("ORCHESTRATOR_BASE_URL", "http://localhost:9000")
http_client = httpx.AsyncClient(timeout=30.0)

class OrcAgentLogicClient:
    """Client to interact with Orchestrator service."""
    
    @staticmethod
    async def call_orchestrator(body: Dict) -> Dict:
        """Fetch prompt template by name from Orchestrator."""
        try:
            print({
                    "X-API-KEY": os.environ.get("ORCHESTRATOR_API_KEY", "h7f5f3e2-3c9d-4e2b-8f4d-1a2b3c4d5e6f"),
                     "Content-Type": "application/json",
                })
            response = await http_client.post(
                f"{ORCHESTRATOR_BASE_URL}/orchestrator",
                json=body,
                headers={
                    "X-API-KEY": os.environ.get("ORCHESTRATOR_API_KEY", "h7f5f3e2-3c9d-4e2b-8f4d-1a2b3c4d5e6f"),
                     "Content-Type": "application/json",
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logging.error(f"Error fetching prompt template: {e}")
            raise

    @classmethod
    async def get_prompt_by_name(cls, prompt_name: str) -> Dict:
        """Fetch prompt template by name from Orchestrator."""
        try:
            body = {
                "type": "rt_voice","ask":"none",
                "conversation_id": None, 
                "rt_action_request" :
                {
                    "type": "get_prompt_template",
                    "payload": {"id": prompt_name}
                }
            }
            response = await cls.call_orchestrator(body)
            return response
        except httpx.HTTPError as e:
            logging.error(f"Error fetching prompt template: {e}")
            raise

    @classmethod
    async def get_default_session_config(cls) -> Dict:
        """Fetch default session configuration from Orchestrator."""
        try:
            body = {
                "type": "rt_voice","ask":"none",
                "conversation_id": None, 
                "rt_action_request" :
                {
                    "type": "get_session_config",
                    "payload": {"name": "default"}
                }
            }
            response = await cls.call_orchestrator(body)
            return response.get("result", {})
        except httpx.HTTPError as e:
            logging.error(f"Error fetching session config: {e}")
            raise
    
if __name__ == "__main__":
    import asyncio

    async def main():
        prompt_name = "default"

        session_config = await OrcAgentLogicClient.get_default_session_config()
        print(f"Default Session Config: {session_config}")

    asyncio.run(main())