"""
This file is responsible for hosting required WebSocket and HTTP endpoints using FastAPI.
"""

import json
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI,Request,HTTPException, WebSocket, WebSocketDisconnect, Response
from azure.core.messaging import CloudEvent

from connectors.acs import AcsConnector
from orchestrator.realtime_client import VoiceAgentClient
from schemas import CallInitiationRequest, CallInitiationResponse
import asyncio

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(openapi_url=None,)

active_sessions = {}

# @app.post(
#     "/initiate_call",
#     response_model=CallInitiationResponse
# )
# async def initiate_call(
#     request: CallInitiationRequest,
#     http_request=Request
# )-> str:
#     """
#     Endpoint to initiate an outbound call via ACS.
#     """
#     try:
        
#         # acs_connector = AcsConnector(
#         #     cognitive_services_endpoint=None
#         # )
#         call_properties = await acs_connector.initiate_call(
#             target_phone_number=request.target_phone_number
#         )
#         return CallInitiationResponse(
#             call_id=call_properties.call_connection_id,
#             status="Call Initiated",
#             target_phone_number=request.target_phone_number,
#             message="The call has been successfully initiated."
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/callbacks")
async def handle_callback(request: Request):
    """Handle incoming call events from ACS"""
    body = await request.body()
    
    # Parse CloudEvents
    events = json.loads(body)
    
    for event_dict in events:
        event_type = event_dict.get("type")
        event_data = event_dict.get("data")
        
        print(f"📞 Event: {event_type}")
        
        if event_type == "Microsoft.Communication.IncomingCall":
            # Answer incoming call
            acs_connector = AcsConnector()
            await acs_connector.handle_incoming_call(event_data)
            voice_session = VoiceAgentClient()
            active_sessions[acs_connector.acs_connection_id] = voice_session
            
    return Response(status_code=200)


@app.websocket("/api/media/{id}")
async def media_websocket(id,websocket: WebSocket):
    """Handle media streaming from ACS"""
    await websocket.accept()
    
    call_connection_id = None
    
    try:
        # First message contains metadata
        metadata_msg = await websocket.receive_text()
        metadata = json.loads(metadata_msg)
        print(f"Media stream metadata: {metadata}")
        call_connection_id = metadata.get("callConnectionId")
        
        print(f"[{id}] 🎵 Media stream connected")
        
        #get first element of active_sessions
        # session = next(iter(active_sessions.values()), None)
        # Get session
        print("active_sessions:", active_sessions)
        voice_session = active_sessions.get(id)
        if not voice_session:
            print(f"[{id}] No active session found")
            await websocket.close()
            return
        
        # Start the voice agent
        await voice_session.start(websocket)
        
    except WebSocketDisconnect:
        print(f"[{call_connection_id}] Media stream disconnected")
    except Exception as e:
        print(f"[{call_connection_id}] Media stream error: {e}")
    finally:
        if id and id in active_sessions:
            await active_sessions[id].cleanup()
            del active_sessions[id]

@app.post("/api/call/outbound")
async def create_outbound_call(request: Request):
    """API endpoint to make an outbound call"""
    body = await request.json()
    phone_number = body.get("phoneNumber")
    
    if not phone_number:
        return {"error": "phoneNumber is required"}
    
    acs_connector = AcsConnector()
    await acs_connector.make_outbound_call(phone_number)
    
    voice_session = VoiceAgentClient()
    print("acs_connector.acs_connection_id:", acs_connector.acs_connection_id)
    active_sessions[acs_connector.acs_connection_id] = voice_session
            
    return {"status": "call initiated", "phoneNumber": phone_number}

# @app.get("/api/health")
# async def health_check():
#     """Health check endpoint"""
#     return {
#         "status": "healthy",
#         "active_sessions": len(active_sessions),
#         "timestamp": datetime.utcnow().isoformat()
#     }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)