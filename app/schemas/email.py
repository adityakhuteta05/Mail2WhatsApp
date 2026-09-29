from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class AttachmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    gmail_attachment_id: str
    filename: str
    mime_type: str
    size: int
    whatsapp_media_id: Optional[str] = None
    status: str = "PENDING"
    error_message: Optional[str] = None


class ParsedEmail(BaseModel):
    gmail_message_id: str
    thread_id: Optional[str] = None
    sender: str
    recipients: str
    subject: str
    date: Optional[str] = None
    received_at: Optional[datetime] = None
    body_text: str
    body_html: Optional[str] = None
    attachments: List[AttachmentSchema] = []
    has_html_fallback: bool = False


class EmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    gmail_message_id: str
    thread_id: Optional[str] = None
    sender: Optional[str] = None
    recipients: Optional[str] = None
    subject: Optional[str] = None
    received_at: Optional[datetime] = None
    status: str
    retry_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime
    attachments: List[AttachmentSchema] = []
