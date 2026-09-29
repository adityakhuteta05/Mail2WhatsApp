import time
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.database import get_db
from app.models.email import Email
from app.models.gmail_account import GmailAccount
from app.schemas.health import DependencyStatus, HealthResponse
from app.services.whatsapp_service import whatsapp_service
from app.utils.logging import logger

router = APIRouter(tags=["Health & Monitoring"])

START_TIME = time.time()


@router.get("/health", response_model=HealthResponse)
def health_check(response: Response, db: Session = Depends(get_db)):
    """
    Application health and dependency status endpoint (FR-14).
    Checks database connection, WhatsApp config, and active account watches.
    """
    is_healthy = True

    # 1. Database check
    db_status = "ok"
    db_details = {}
    try:
        db.execute(text("SELECT 1"))
        db_details["connection"] = "alive"
    except Exception as e:
        is_healthy = False
        db_status = "error"
        db_details["error"] = str(e)
        logger.error(f"Health check DB failure: {e}")

    # 2. WhatsApp configuration check
    wa_configured = whatsapp_service.is_configured
    wa_status = DependencyStatus(
        status="configured" if wa_configured else "unconfigured_or_mock",
        details={
            "phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID if wa_configured else "not_set",
            "api_version": settings.WHATSAPP_API_VERSION,
            "recipient_configured": bool(settings.WHATSAPP_RECIPIENT_NUMBER),
        },
    )

    # 3. Pub/Sub configuration check
    pubsub_status = DependencyStatus(
        status="configured" if bool(settings.GMAIL_PUBSUB_TOPIC) else "unconfigured",
        details={"topic": settings.GMAIL_PUBSUB_TOPIC or "not_set"},
    )

    # 4. Metrics
    active_accounts = 0
    pending_emails = 0
    try:
        if db_status == "ok":
            active_accounts = db.query(GmailAccount).filter(GmailAccount.is_active == True).count()
            pending_emails = db.query(Email).filter(Email.status.in_(["PROCESSING", "RETRY_WAIT"])).count()
    except Exception:
        pass

    uptime_sec = round(time.time() - START_TIME, 2)
    overall_status = "healthy" if is_healthy else "unhealthy"

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status=overall_status,
        version=__version__,
        environment=settings.APP_ENV,
        uptime_seconds=uptime_sec,
        database=DependencyStatus(status=db_status, details=db_details),
        whatsapp_api=wa_status,
        pubsub_topic=pubsub_status,
        active_gmail_accounts=active_accounts,
        pending_emails=pending_emails,
    )


@router.get("/health/ready")
def readiness_check(response: Response, db: Session = Depends(get_db)):
    """
    Kubernetes/Cloud Run readiness probe.
    Returns 200 if the app is ready to accept traffic.
    """
    try:
        db.execute(text("SELECT 1"))
        return {"ready": True}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ready": False, "error": str(e)}
