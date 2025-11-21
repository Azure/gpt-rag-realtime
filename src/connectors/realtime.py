

import asyncio
import json
import os
import websockets
import logging
from datetime import datetime, timezone

from utils.event import RealtimeEventHandler

class RealtimeAPI(RealtimeEventHandler):
    def __init__(self):
        super().__init__()
        
        # Additional initialization for the real-time API
        self.ws = None
        self.openai_endpoint = os.getenv("OPENAI_API_BASE")
        if not self.openai_endpoint:
            raise ValueError("OPENAI_API_BASE environment variable is not set.")
        if self.openai_endpoint.startswith("https://"):
            self.openai_endpoint = self.openai_endpoint.replace("https://","wss://")
        #!TODO will change later to managed identity
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        self.api_version = os.getenv("OPENAI_API_VERSION", "2024-10-01-preview")
        self.azure_model_deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4-turbo")

    async def _receive_messages(self,**kwargs):
        """
        Internal method to receive messages from the WebSocket.
        """
        print("Receiving messages from WebSocket...")
        try:
            async for message in self.ws:
                event = json.loads(message)
                logging.info(f"[Websocket]Received message: {message}")
                if event.get("type") == "error":
                    logging.error(f"[Websocket]Error event received: {event}")
                self.dispatch(f"server.{event.get('type')}", event, **kwargs)
                # self.dispatch("server.*", event, **kwargs)
        except websockets.ConnectionClosed:
            logging.warning("[Websocket]Connection closed.")

    async def connect(self):
        """
        Connect to the real-time API WebSocket.
        """

        if self.ws is not None:
            raise RuntimeError("WebSocket is already connected.")

        ws_url = f"{self.openai_endpoint}/openai/realtime?api-version={self.api_version}&deployment={self.azure_model_deployment_name}"
        
        self.ws = await websockets.connect(
            ws_url,
            additional_headers={
                "api-key": self.api_key,
                # "Content-Type": "application/json"
            }
        )
        logging.info("[Websocket]Connected to the real-time API WebSocket.")
        return True
    
    async def send(self, event_name, data=None):
        """
        Send a message to the WebSocket.
        
        :param event_name: Name of the event to send.
        :param data: Data payload for the event.
        """
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected.")

        if data is None:
            data = {}
        elif not isinstance(data, dict):
            raise ValueError("Data must be a dictionary.")
        
        event = {
            "event_id": self._generate_event_id("evt_"),
            "type": event_name,**data
        }
        
        logging.info(f"[Websocket]Sent message: {event}")
        await self.ws.send(json.dumps(event))
        

    def _generate_event_id(self, prefix="evt_"):
        """
        Generate a unique event ID using the current timestamp.
        
        :param prefix: Prefix for the event ID.
        :return: A unique event ID string.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        return f"{prefix}{timestamp}"
    
    async def disconnect(self):
        """
        Disconnect from the real-time API WebSocket.
        """
        if self.ws is not None:
            await self.ws.close()
            self.ws = None
            logging.info("[Websocket]Disconnected from the real-time API WebSocket.")
