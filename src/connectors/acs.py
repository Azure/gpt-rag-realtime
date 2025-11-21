import os

from azure.communication.callautomation import (
    CallAutomationClient,
    MediaStreamingOptions,
    AudioFormat,
    MediaStreamingTransportType,
    MediaStreamingContentType,
    MediaStreamingAudioChannelType,
    PhoneNumberIdentifier,
    CallInvite,
)

import uuid
class AcsConnector:
    def __init__(
        self,        
        cognitive_services_endpoint: str= None,
        websocket_url: str= os.getenv("ACS_WEBSOCKET_URL"),
        callback_url: str= os.getenv("ACS_CALLBACK_URL"),
        source_number: str = os.getenv("ACS_PHONE_NUMBER"),
        acs_connection_string: str= os.getenv("ACS_CONNECTION_STRING"),
    ):
         
        self.acs_connection_id = uuid.uuid4().hex
        if not acs_connection_string:
             raise ValueError("ACS_CONNECTION_STRING environment variable is not set.")
        
        if not source_number:
             raise ValueError("ACS_PHONE_NUMBER environment variable is not set.")  
        
        self.acs_client = CallAutomationClient.from_connection_string(acs_connection_string)
        self.source_number = source_number
        self.callback_url = callback_url
        self.cognitive_service_endpoint = cognitive_services_endpoint

        self.media_streaming_options = MediaStreamingOptions(
                transport_url=f"{websocket_url}/{self.acs_connection_id}",
                transport_type=MediaStreamingTransportType.WEBSOCKET,
                content_type=MediaStreamingContentType.AUDIO,
                audio_channel_type=MediaStreamingAudioChannelType.MIXED,
                start_media_streaming=True,
                enable_bidirectional=True,
                audio_format=AudioFormat.PCM24_K_MONO
        )

    async def make_outbound_call(self, target_phone_number: str):
        """
        Initiate an outbound call to the specified target phone number.
        """
    
        target_participant = PhoneNumberIdentifier(target_phone_number)
        source_caller = PhoneNumberIdentifier(self.source_number)

        call_conn_properties = self.acs_client.create_call(
            target_participant, 
            self.callback_url,
            cognitive_services_endpoint=self.cognitive_service_endpoint,
            source_caller_id_number=source_caller,
            media_streaming=self.media_streaming_options
        )
        return call_conn_properties
    
    async def handle_incoming_call(self, event_data: dict):
        """Answer incoming call and set up media streaming"""
        try:
            incoming_call_context = event_data.get("incomingCallContext")
            caller_id = event_data.get("from", {}).get("rawId", "Unknown")

            
            #Answer streaming configuration
            answer_call_result = self.acs_client.answer_call(
                incoming_call_context=incoming_call_context,
                callback_url=self.callback_url,
                media_streaming= self.media_streaming_options
            )

            return True
        except Exception as e:
            pass
    
