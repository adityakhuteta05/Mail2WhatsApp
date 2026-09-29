from datetime import datetime
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import verify_pubsub_request
from app.models.delivery import DeliveryLog
from app.models.email import Email
from app.schemas.webhook import PubSubPushRequest, WhatsAppWebhookPayload
from app.services.pubsub_service import PubSubService
from app.services.sync_service import SyncService
from app.utils.logging import logger
from app.utils.security import verify_whatsapp_signature

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


@router.post(
    "/google-pubsub",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_pubsub_request)],
)
async def receive_google_pubsub_push(
    request_data: PubSubPushRequest,
    db: Session = Depends(get_db),
):
    """
    Receives and acknowledges Google Cloud Pub/Sub push notifications (FR-03).
    Decodes the mailbox change payload and kicks off the processing pipeline.
    """
    try:
        decoded = PubSubService.decode_push_notification(request_data)
        logger.info(
            f"Received Pub/Sub event for mailbox: {decoded.emailAddress}, historyId: {decoded.historyId}"
        )

        processed_count = await SyncService.process_mailbox_notification(
            email_address=decoded.emailAddress,
            incoming_history_id=decoded.historyId,
            db=db,
        )

        return {
            "status": "acknowledged",
            "emailAddress": decoded.emailAddress,
            "processed": processed_count,
        }

    except ValueError as ve:
        logger.warning(f"Invalid Pub/Sub payload received: {ve}")
        # Return 200 to acknowledge and drop bad poison-pill messages
        return {"status": "dropped", "reason": str(ve)}
    except Exception as e:
        logger.error(f"Error handling Pub/Sub push notification: {e}", exc_info=True)
        # Return 500 so Pub/Sub will backoff and retry according to its policy
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transient failure processing Pub/Sub notification. Retrying.",
        )


@router.get("/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """
    Meta WhatsApp Cloud API Webhook verification endpoint (PRD Section 11).
    Responds to the Hub challenge if the verify token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully.")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning("WhatsApp webhook verification failed: token mismatch.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


@router.post("/whatsapp")
async def receive_whatsapp_status(
    payload: WhatsAppWebhookPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receives delivery status notifications from WhatsApp Cloud API (FR-11).
    Updates delivery tracking state (sent, delivered, read, failed).
    """
    try:
        if not payload.entry:
            return {"status": "ignored", "reason": "No entry in payload"}

        updated_logs = 0

        for entry in payload.entry:
            for change in entry.changes:
                val = change.value
                if not val or not val.statuses:
                    continue

                for st in val.statuses:
                    wamid = st.id
                    new_status = st.status.lower()

                    # Find delivery log matching this WhatsApp message ID
                    log_entry = (
                        db.query(DeliveryLog)
                        .filter(DeliveryLog.whatsapp_message_id == wamid)
                        .first()
                    )

                    if not log_entry:
                        logger.debug(f"Status update for unknown wamid: {wamid}")
                        continue

                    log_entry.status = new_status
                    ts_dt = datetime.utcnow()
                    try:
                        if st.timestamp:
                            ts_dt = datetime.utcfromtimestamp(int(st.timestamp))
                    except Exception:
                        pass

                    if new_status == "delivered":
                        log_entry.delivered_at = ts_dt
                    elif new_status == "read":
                        log_entry.read_at = ts_dt
                    elif new_status == "failed":
                        err_text = ""
                        if st.errors:
                            err_text = "; ".join(f"{e.code}: {e.message or e.title}" for e in st.errors)
                        log_entry.error = err_text

                    # Update parent Email status if appropriate
                    email_parent = log_entry.email
                    if email_parent:
                        if new_status in ["delivered", "read"] and email_parent.status in ["SENT", "DELIVERY_PENDING"]:
                            email_parent.status = new_status.upper()
                        elif new_status == "failed" and email_parent.status != "DELIVERED":
                            email_parent.status = "FAILED"
                            email_parent.error_message = log_entry.error

                    updated_logs += 1

        db.commit()
        return {"status": "ok", "updated": updated_logs}

    except Exception as e:
        logger.error(f"Error handling WhatsApp status webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
