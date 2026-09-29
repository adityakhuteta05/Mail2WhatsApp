import base64
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from app.config import settings
from app.utils.logging import logger
from app.utils.security import decrypt_token, encrypt_token

# Allow HTTP redirect for local development
if settings.APP_ENV != "production":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]


_PKCE_VERIFIERS: Dict[str, str] = {}


class GmailService:
    """
    Gmail API integration service for OAuth, mailbox watch, history sync,
    message retrieval, and attachment fetching.
    """

    @classmethod
    def get_oauth_flow(cls, state: Optional[str] = None) -> Flow:
        """Constructs Google OAuth 2.0 Flow instance."""
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=GMAIL_SCOPES,
            state=state,
        )
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
        # Confidential server clients use client_secret; disable PKCE autogen or store verifier
        flow.autogenerate_code_verifier = False
        return flow

    @classmethod
    def get_authorization_url(cls, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Generates Google OAuth 2.0 authorization URL requesting offline access
        and forced consent to receive a durable refresh token.
        """
        flow = cls.get_oauth_flow(state=state)
        authorization_url, generated_state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        if flow.code_verifier:
            _PKCE_VERIFIERS[generated_state] = flow.code_verifier
        return authorization_url, generated_state

    @classmethod
    def exchange_code_for_credentials(cls, code: str, state: Optional[str] = None) -> Credentials:
        """Exchanges the OAuth 2.0 authorization code for user credentials."""
        flow = cls.get_oauth_flow(state=state)
        verifier = _PKCE_VERIFIERS.pop(state, None) if state else None
        flow.fetch_token(code=code, code_verifier=verifier)
        return flow.credentials

    @classmethod
    def build_credentials(
        cls,
        refresh_token_encrypted: str,
        access_token: Optional[str] = None,
        token_expiry: Optional[datetime] = None,
    ) -> Credentials:
        """Constructs Google Credentials object from encrypted stored tokens."""
        plain_refresh = decrypt_token(refresh_token_encrypted)
        return Credentials(
            token=access_token,
            refresh_token=plain_refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=GMAIL_SCOPES,
            expiry=token_expiry,
        )

    @classmethod
    def get_client(cls, credentials: Credentials) -> Resource:
        """Returns an authorized Gmail API v1 resource client."""
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    @classmethod
    def get_user_profile(cls, service: Resource) -> Dict[str, Any]:
        """Fetches primary email address and account info."""
        return service.users().getProfile(userId="me").execute()

    @classmethod
    def setup_watch(cls, service: Resource, topic_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Registers Gmail push notifications with Google Cloud Pub/Sub topic (PRD Section 8).
        Body: {'topicName': ..., 'labelIds': ['INBOX']}
        Returns: {'historyId': '...', 'expiration': '1727000000000'}
        """
        topic = topic_name or settings.GMAIL_PUBSUB_TOPIC
        if not topic:
            raise ValueError("GMAIL_PUBSUB_TOPIC must be configured to set up Gmail watch.")
        
        request_body = {
            "topicName": topic,
            "labelIds": ["INBOX"],
        }
        logger.info(f"Registering Gmail watch against topic: {topic}")
        response = service.users().watch(userId="me", body=request_body).execute()
        return response

    @classmethod
    def stop_watch(cls, service: Resource) -> None:
        """Stops Gmail push notifications for the mailbox."""
        try:
            service.users().stop(userId="me").execute()
            logger.info("Successfully stopped Gmail watch.")
        except Exception as e:
            logger.warning(f"Error stopping Gmail watch: {e}")

    @classmethod
    def get_history_changes(
        cls,
        service: Resource,
        start_history_id: str,
    ) -> Tuple[List[str], Optional[str]]:
        """
        Queries Gmail History API for changes after start_history_id.
        Extracts new message IDs (messagesAdded).
        Returns (list_of_message_ids, latest_history_id).
        """
        discovered_message_ids = []
        page_token = None
        latest_history_id = start_history_id

        while True:
            response = service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                pageToken=page_token,
            ).execute()

            history_items = response.get("history", [])
            for item in history_items:
                if "messagesAdded" in item:
                    for added in item["messagesAdded"]:
                        msg = added.get("message", {})
                        msg_id = msg.get("id")
                        # Filter to messages in INBOX
                        labels = msg.get("labelIds", [])
                        if msg_id and ("INBOX" in labels or not labels):
                            discovered_message_ids.append(msg_id)

            if "historyId" in response:
                latest_history_id = response["historyId"]

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        # Deduplicate while preserving order
        unique_ids = list(dict.fromkeys(discovered_message_ids))
        return unique_ids, latest_history_id

    @classmethod
    def get_message(cls, service: Resource, message_id: str, format: str = "full") -> Dict[str, Any]:
        """Retrieves complete message details by ID."""
        return service.users().messages().get(userId="me", id=message_id, format=format).execute()

    @classmethod
    def get_attachment_bytes(cls, service: Resource, message_id: str, attachment_id: str) -> bytes:
        """
        Retrieves raw attachment bytes via users.messages.attachments.get.
        Decodes base64 URL-safe payload.
        """
        res = service.users().messages().attachments().get(
            userId="me",
            messageId=message_id,
            id=attachment_id,
        ).execute()

        data_str = res.get("data", "")
        padded = data_str + "=" * ((4 - len(data_str) % 4) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8"))

    @classmethod
    def list_recent_messages(
        cls,
        service: Resource,
        query: str = "newer_than:7d label:INBOX",
        max_results: int = 50,
    ) -> List[str]:
        """
        Fallback message query for reconciliation when Gmail history window has expired.
        """
        response = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results,
        ).execute()

        messages = response.get("messages", [])
        return [m["id"] for m in messages if "id" in m]


gmail_service = GmailService()
