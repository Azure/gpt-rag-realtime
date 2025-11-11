
import os
from azure.communication.callautomation import (
    MediaStreamingOptions,
    AudioFormat,
    MediaStreamingTransportType,
    MediaStreamingContentType,
    MediaStreamingAudioChannelType,
    CallAutomationClient,
    PhoneNumberIdentifier
)


class AcsConnector:
    """
    Helper class for Azure Communication Services calling functionality.
    """
    def __init__(self):
        self.acs_connection_string = os.getenv("ACS_CONNECTION_STRING")
        if not self.acs_connection_string:
            raise ValueError("ACS_CONNECTION_STRING environment variable is not set.")
        self.acs_client = CallAutomationClient.from_connection_string(self.acs_connection_string)

        self.acs_phone_number = os.getenv("ACS_PHONE_NUMBER")
        self.ws_url = os.getenv("ACS_WEBSOCKET_URL")
        self.cognitive_service_endpoint = os.getenv("COGNITIVE_SERVICES_ENDPOINT")
        self.callback_url = os.getenv("CALLBACK_URI_HOST")
        self.callback_events_uri = f"{self.callback_url}/api/callbacks"

    async def initiate_call(self, target_phone_number, participant_number):
        """
        
        """
        target_participant = PhoneNumberIdentifier(target_phone_number)
        source_caller = PhoneNumberIdentifier(self.acs_phone_number)

        # !TODO Update the live agent phone number in ragtools

        media_streaming_options = MediaStreamingOptions(
            transport_url=self.ws_url,
            transport_type=MediaStreamingTransportType.WEBSOCKET,
            content_type=MediaStreamingContentType.AUDIO,
            audio_channel_type=MediaStreamingAudioChannelType.MIXED,
            start_media_streaming=True,
            enable_bidirectional=True,
            audio_format=AudioFormat.PCM24_K_MONO
        )

        call_conn_properties = self.acs_client.create_call(
            target_participant, 
            self.callback_events_uri,
            cognitive_services_endpoint=self.cognitive_service_endpoint,
            source_caller_id_number=source_caller,
            media_streaming=media_streaming_options
        )
        return call_conn_properties
    
    async def answer_incoming_call(self, incoming_call_context):
        pass
    
