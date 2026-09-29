from fastapi import Depends, HTTPException, Header, Query, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.utils.security import verify_pubsub_token, verify_whatsapp_signature


def get_database(db: Session = Depends(get_db)) -> Session:
    """Convenience alias for DB dependency."""
    return db


async def verify_pubsub_request(
    request: Request,
    token: str = Query(None, alias="token"),
    x_pubsub_token: str = Header(None, alias="X-Pubsub-Token"),
) -> None:
    """
    Validates optional Pub/Sub push token in query param or header if PUBSUB_VERIFICATION_TOKEN is set.
    """
    if not settings.PUBSUB_VERIFICATION_TOKEN:
        return

    provided = token or x_pubsub_token
    if not verify_pubsub_token(provided):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing Pub/Sub verification token",
        )
