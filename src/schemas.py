from typing import Optional
from pydantic import BaseModel, Field


class CallInitiationRequest(BaseModel):
    target_phone_number: str = Field(..., description="The phone number to initiate the call to.")

class CallInitiationResponse(BaseModel):
    call_id: str = Field(..., description="The unique identifier for the initiated call.")
    status: str = Field(..., description="The status of the call initiation.")
    target_phone_number: str = Field(..., description="The phone number the call was initiated to.")
    message: Optional[str] = Field(None, description="Additional information about the call initiation.")