from typing import Optional, Dict, Any
from pydantic import BaseModel


class DependencyStatus(BaseModel):
    status: str
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str  # healthy, degraded, unhealthy
    version: str
    environment: str
    uptime_seconds: float
    database: DependencyStatus
    whatsapp_api: DependencyStatus
    pubsub_topic: DependencyStatus
    active_gmail_accounts: int
    pending_emails: int
