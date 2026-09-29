from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.gmail_account import GmailAccount
from app.schemas.auth import OAuthCallbackResponse, OAuthUrlResponse
from app.services.gmail_service import GmailService
from app.utils.logging import logger
from app.utils.security import encrypt_token

router = APIRouter(prefix="/auth", tags=["Google OAuth"])


@router.get("/google/login", response_model=OAuthUrlResponse)
def google_oauth_login(
    redirect: bool = Query(False, description="If true, directly redirects browser to Google OAuth"),
    state: Optional[str] = Query(None, description="Optional CSRF state parameter"),
):
    """
    Generates Google OAuth 2.0 authorization URL for connecting a Gmail account.
    """
    try:
        auth_url, gen_state = GmailService.get_authorization_url(state=state)
        if redirect:
            return RedirectResponse(url=auth_url)
        return OAuthUrlResponse(
            authorization_url=auth_url,
            message="Navigate to authorization_url in browser to grant Gmail read permissions.",
        )
    except Exception as e:
        logger.error(f"Failed to generate Google OAuth URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Google OAuth authorization URL: {str(e)}",
        )


@router.get("/google/callback", response_model=OAuthCallbackResponse)
def google_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State passed to OAuth"),
    db: Session = Depends(get_db),
):
    """
    OAuth 2.0 redirect callback. Exchanges code for tokens, encrypts refresh token,
    registers or updates account, and sets up Gmail mailbox watch.
    """
    try:
        credentials = GmailService.exchange_code_for_credentials(code=code, state=state)
        if not credentials.refresh_token:
            logger.warning("No refresh token received. User might have previously authorized.")

        # Build authenticated Gmail service to discover user email
        service = GmailService.get_client(credentials)
        profile = GmailService.get_user_profile(service)
        email_address = profile.get("emailAddress")

        if not email_address:
            raise ValueError("Unable to determine user email from Gmail profile.")

        # Encrypt refresh token
        encrypted_refresh = encrypt_token(credentials.refresh_token or "")

        # Lookup or create account
        account = db.query(GmailAccount).filter(GmailAccount.email == email_address).first()
        if not account:
            account = GmailAccount(
                email=email_address,
                refresh_token_ref=encrypted_refresh,
                access_token=credentials.token,
                token_expiry=credentials.expiry,
                is_active=True,
            )
            db.add(account)
        else:
            if credentials.refresh_token:
                account.refresh_token_ref = encrypted_refresh
            account.access_token = credentials.token
            account.token_expiry = credentials.expiry
            account.is_active = True

        db.commit()
        db.refresh(account)

        # Attempt initial watch registration
        history_id = None
        watch_expiry = None
        try:
            watch_res = GmailService.setup_watch(service)
            if "historyId" in watch_res:
                history_id = str(watch_res["historyId"])
                account.history_id = history_id
            if "expiration" in watch_res:
                exp_ms = int(watch_res["expiration"])
                watch_expiry = datetime.utcfromtimestamp(exp_ms / 1000.0)
                account.watch_expiry = watch_expiry
            db.commit()
            logger.info(f"Gmail watch established for {email_address} (expires: {watch_expiry})")
        except Exception as watch_err:
            logger.warning(
                f"Account connected, but watch registration deferred (topic may not be configured yet): {watch_err}"
            )

        return OAuthCallbackResponse(
            status="connected",
            email=email_address,
            history_id=history_id or account.history_id,
            watch_expiry=watch_expiry or account.watch_expiry,
            message=f"Gmail account {email_address} connected successfully.",
        )

    except Exception as e:
        logger.error(f"Error handling Google OAuth callback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth callback failed: {str(e)}",
        )
