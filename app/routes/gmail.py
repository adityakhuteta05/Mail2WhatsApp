from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.email import Email
from app.models.gmail_account import GmailAccount
from app.schemas.auth import GmailAccountResponse
from app.schemas.email import EmailResponse
from app.services.sync_service import SyncService
from app.utils.logging import logger

router = APIRouter(prefix="/gmail", tags=["Gmail Management"])


@router.get("/accounts", response_model=List[GmailAccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    """Lists all connected Gmail accounts and their watch status."""
    return db.query(GmailAccount).all()


@router.post("/watch/renew")
def renew_watches(db: Session = Depends(get_db)):
    """
    Manually triggers renewal of any expiring Gmail mailbox watches (FR-02).
    """
    try:
        renewed = SyncService.check_and_renew_watches(db)
        return {"status": "ok", "watches_renewed": renewed}
    except Exception as e:
        logger.error(f"Error renewing watches: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/reconcile")
async def trigger_reconciliation(
    email: Optional[str] = Query(None, description="Optional specific email account to reconcile"),
    db: Session = Depends(get_db),
):
    """
    Triggers recovery reconciliation to find and process any missed emails (FR-12).
    """
    try:
        query = db.query(GmailAccount).filter(GmailAccount.is_active == True)
        if email:
            query = query.filter(GmailAccount.email == email)
        accounts = query.all()

        if not accounts:
            return {"status": "ok", "message": "No active accounts found", "processed": 0}

        total_processed = 0
        for acc in accounts:
            processed = await SyncService.reconcile_account(account=acc, db=db)
            total_processed += processed

        return {
            "status": "ok",
            "accounts_checked": len(accounts),
            "messages_recovered": total_processed,
        }
    except Exception as e:
        logger.error(f"Reconciliation error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/emails", response_model=List[EmailResponse])
def list_emails(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """Lists recently processed/discovered emails with delivery status."""
    query = db.query(Email)
    if status_filter:
        query = query.filter(Email.status == status_filter.upper())
    emails = query.order_by(Email.id.desc()).offset(offset).limit(limit).all()
    return emails


@router.post("/retry")
def retry_failed_emails(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Resets failed emails back to RETRY_WAIT with an immediate retry window
    so the background worker can re-attempt dispatching them.
    """
    from datetime import datetime
    failed_emails = (
        db.query(Email)
        .filter(Email.status == "FAILED")
        .order_by(Email.id.desc())
        .limit(limit)
        .all()
    )
    for email in failed_emails:
        email.status = "RETRY_WAIT"
        email.next_retry_at = datetime.utcnow()
        email.retry_count = 0
    db.commit()
    return {"status": "ok", "queued_for_retry": len(failed_emails)}
