from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class OAuthUrlResponse(BaseModel):
    authorization_url: str
    message: str


class OAuthCallbackResponse(BaseModel):
    status: str
    email: str
    history_id: Optional[str] = None
    watch_expiry: Optional[datetime] = None
    message: str


class GmailAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    history_id: Optional[str] = None
    watch_expiry: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
