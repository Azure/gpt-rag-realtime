from typing import Optional
import asyncio
import json
import base64
from fastapi import WebSocket

from utils.event import RealtimeEventHandler
from utils.common import _read_prompt_from_txt, array_buffer_to_base64, recieve_audio_for_outbound_call, stop_audio

from connectors.realtime import RealtimeAPI

class VoiceAgentClient(RealtimeEventHandler):
    """
    Responsible for defining agents, attaching tools, and managing sessions.
    """
    def __init__(self, acs_ws=None):
        super().__init__()
        self.system_prompt = _read_prompt_from_txt("agents/prompts/main.txt")
        self.model: Optional[str]= None
        self.temperature: Optional[float] = 0.7
        self.max_response_output_tokens: Optional[int] = 1024
        self.voice: Optional[str] = "alloy"
        self.tools: list = []  # List of tools to be attached to the agent
        self.realtime = RealtimeAPI()
        self.default_session_config: dict = {
            # "id": "sessionId",
            "turn_detection": {
                "type": "server_vad",
                "threshold": .6,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500
            },
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            # "model": self.model,
            "temperature": self.temperature,
            "max_response_output_tokens": self.max_response_output_tokens,
            "instructions": self.system_prompt,
            "voice": self.voice,
            "tool_choice":"auto" if len(self.tools) > 0 else "none",
            "tools": self.tools
        }
        self.session_config = self.default_session_config.copy()
        self._realtime_api_event_handler()
        self.is_active = True
        self.acs_ws = acs_ws
    
    async def connect(self):
        """
        Connect to the real-time API.
        """
        if self.realtime.ws is not None:
            raise RuntimeError("WebSocket is already connected.")
        await self.realtime.connect()
        await self.update_session()
        return True
    
    def is_connected(self) -> bool:
        """
        Check if the client is connected to the real-time API.
        """
        return self.realtime.ws is not None

    async def update_session(self, **kwargs):
        """
        Update session configuration.
        """
        self.session_config.update(kwargs)
        if self.realtime.ws is not None:
            await self.realtime.send(
                "session.update",
                {"session": self.session_config}
            )
        return True
    
    async def handle_acs_audio_to_openai(self):
        try:
            while self.is_active and self.acs_ws:
                try:
                    # Receive audio from ACS Websocket
                    message = await asyncio.wait_for(
                        self.acs_ws.receive_text(),
                        timeout=1.0
                    )
                    data = json.loads(message)
                    
                    if data.get("kind") == "AudioData":
                        # Extract audio from ACS
                        audio_base64 = data.get("audioData", {}).get("data","")
                        if audio_base64:
                            # Decode from base54
                            audio_16khz = base64.b64decode(audio_base64)
                            # !TODO Need to resample
                            audio_message = {
                                "audio": base64.b64encode(audio_16khz).decode('utf-8')
                            }
                            await self.realtime.send(
                                "input_audio_buffer.append",
                                audio_message
                            )
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print("Error while in ACS -> OpenAI ",e)
                    break
        except Exception as e:
            print("Fatal error in audio strem")

    # async def handle_openai_audio_to_acs(self):
    #     try:
    #         await self.realtime._receive_messages()
    #     except Exception as e:
    #         print("Fatal error in audio stream OpenAI -> ACS",e)

    async def start(self, acs_ws: WebSocket):
        self.acs_ws = acs_ws
        try:
            await self.connect()

            await asyncio.gather(
                self.handle_acs_audio_to_openai(),
                self.realtime._receive_messages()  #
            )
        except Exception as e:
            print("session error",e)
        finally:
            await self.cleanup()

    def _realtime_api_event_handler(self):
        """
        Handle event from both client and server sides.
        """
        self.realtime.on("client.*", self._on_logging_event)
        self.realtime.on("server.*", self._on_logging_event)
        self.realtime.on("server.response.audio.delta", self._on_response_audio_delta)
    
    async def _on_logging_event(self, event):
        print("testing ")

    async def _on_response_audio_delta(self, event):
        audio_base64 = event.get("delta","")
        if audio_base64 and self.acs_ws:
            audio_24khz = base64.b64decode(audio_base64)

            acs_message = {
                "kind": "AudioData",
                "audioData": {
                    "data": base64.b64encode(audio_24khz).decode('utf-8')
                }
            }
            await self.acs_ws.send_text(json.dumps(acs_message))

    def disconnect(self):
        """
        Disconnect from the real-time API.
        """
        if self.realtime.ws is not None:
            return self.realtime.disconnect()
    
    async def cleanup(self):
        self.is_active = False
        await self.realtime.disconnect()
        
