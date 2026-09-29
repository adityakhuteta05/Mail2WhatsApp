from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# --- Google Cloud Pub/Sub Models ---

class PubSubMessage(BaseModel):
    data: str  # Base64-encoded string
    messageId: Optional[str] = None
    publishTime: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class PubSubPushRequest(BaseModel):
    message: PubSubMessage
    subscription: Optional[str] = None


class GmailPubSubData(BaseModel):
    emailAddress: str
    historyId: str


# --- WhatsApp Webhook Models ---

class WhatsAppStatusError(BaseModel):
    code: int
    title: Optional[str] = None
    message: Optional[str] = None
    error_data: Optional[Dict[str, Any]] = None


class WhatsAppStatusItem(BaseModel):
    id: str  # WhatsApp message ID (wamid)
    status: str  # sent, delivered, read, failed
    timestamp: str
    recipient_id: Optional[str] = None
    errors: Optional[List[WhatsAppStatusError]] = None


class WhatsAppValue(BaseModel):
    messaging_product: Optional[str] = "whatsapp"
    metadata: Optional[Dict[str, Any]] = None
    statuses: Optional[List[WhatsAppStatusItem]] = None
    messages: Optional[List[Dict[str, Any]]] = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    object: Optional[str] = None
    entry: Optional[List[WhatsAppEntry]] = None
