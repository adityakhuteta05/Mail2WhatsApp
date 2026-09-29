from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from googleapiclient.errors import HttpError

from app.config import settings
from app.models.gmail_account import GmailAccount
from app.models.email import Email
from app.models.attachment import Attachment
from app.models.delivery import DeliveryLog
from app.models.sync_run import SyncRun
from app.services.gmail_service import GmailService, gmail_service
from app.services.mime_parser import MIMEParser
from app.services.attachment_service import attachment_service
from app.services.whatsapp_service import WhatsAppService, whatsapp_service
from app.services.retry_service import retry_service
from app.utils.logging import logger


class SyncService:
    """
    Orchestrates the end-to-end event-driven message discovery,
    retrieval, deduplication, formatting, forwarding, and reconciliation pipeline.
    """

    @classmethod
    async def process_mailbox_notification(
        cls,
        email_address: str,
        incoming_history_id: str,
        db: Session,
        wa_service: Optional[WhatsAppService] = None,
    ) -> int:
        """
        Triggered when a Pub/Sub push notification is received.
        Fetches Gmail history changes, deduplicates, retrieves email content,
        and forwards to WhatsApp.
        Returns the count of successfully processed new messages.
        """
        account = db.query(GmailAccount).filter(GmailAccount.email == email_address).first()
        if not account:
            logger.warning(f"Pub/Sub received for unknown/unregistered account: {email_address}")
            return 0

        if not account.is_active:
            logger.info(f"Account {email_address} is marked inactive. Skipping sync.")
            return 0

        wa_svc = wa_service or whatsapp_service
        start_history_id = account.history_id or incoming_history_id

        # Build authenticated Gmail client
        creds = GmailService.build_credentials(
            refresh_token_encrypted=account.refresh_token_ref,
            access_token=account.access_token,
            token_expiry=account.token_expiry,
        )
        gmail_client = GmailService.get_client(creds)

        discovered_ids = []
        new_latest_history_id = incoming_history_id

        try:
            discovered_ids, new_latest_history_id = GmailService.get_history_changes(
                service=gmail_client,
                start_history_id=start_history_id,
            )
        except HttpError as e:
            # Check if historyId has expired (404 Not Found)
            if e.resp.status == 404:
                logger.warning(
                    f"History ID {start_history_id} expired for {email_address}. Triggering reconciliation fallback."
                )
                return await cls.reconcile_account(account=account, db=db, wa_service=wa_svc)
            else:
                logger.error(f"Gmail history query error: {e}")
                raise

        logger.info(
            f"Discovered {len(discovered_ids)} new message(s) for {email_address}. Latest historyId: {new_latest_history_id}"
        )

        processed_count = 0
        for msg_id in discovered_ids:
            success = await cls.process_single_message(
                gmail_client=gmail_client,
                account=account,
                message_id=msg_id,
                db=db,
                wa_service=wa_svc,
            )
            if success:
                processed_count += 1

        # Advance stored historyId to prevent reprocessing
        if new_latest_history_id:
            account.history_id = str(new_latest_history_id)
            db.commit()

        return processed_count

    @classmethod
    async def process_single_message(
        cls,
        gmail_client,
        account: GmailAccount,
        message_id: str,
        db: Session,
        wa_service: WhatsAppService,
    ) -> bool:
        """
        Processes an individual Gmail message by ID:
        1. Atomic deduplication check
        2. Retrieve full email payload from Gmail API
        3. Parse MIME headers, body, attachments
        4. Forward text to WhatsApp
        5. Forward attachments to WhatsApp
        6. Record delivery logs & state transitions
        """
        # --- Deduplication (FR-09) ---
        existing_email = db.query(Email).filter(Email.gmail_message_id == message_id).first()
        if existing_email:
            logger.info(f"Duplicate detected: Gmail message {message_id} already exists with status {existing_email.status}. Skipping.")
            return False

        # Create record in DISCOVERED state
        email_record = Email(
            account_id=account.id,
            gmail_message_id=message_id,
            status="DISCOVERED",
        )
        db.add(email_record)
        try:
            db.commit()
            db.refresh(email_record)
        except Exception as e:
            # In case of concurrent insert race condition
            db.rollback()
            logger.warning(f"Concurrent insert detected for {message_id}: {e}")
            return False

        # Transition to PROCESSING
        email_record.status = "PROCESSING"
        db.commit()

        recipient_number = settings.WHATSAPP_RECIPIENT_NUMBER
        if not recipient_number:
            logger.error("No WHATSAPP_RECIPIENT_NUMBER configured.")
            email_record.status = "FAILED"
            email_record.error_message = "No WHATSAPP_RECIPIENT_NUMBER configured"
            db.commit()
            return False

        try:
            # 1. Retrieve full message from Gmail
            msg_payload = GmailService.get_message(
                service=gmail_client,
                message_id=message_id,
                format="full",
            )

            # 2. Parse MIME data
            parsed = MIMEParser.parse_gmail_api_message(msg_payload)

            email_record.thread_id = parsed.thread_id
            email_record.sender = parsed.sender
            email_record.recipients = parsed.recipients
            email_record.subject = parsed.subject
            if parsed.date:
                # Attempt to parse standard RFC email date
                try:
                    import email.utils
                    parsed_tuple = email.utils.parsedate_to_datetime(parsed.date)
                    email_record.received_at = parsed_tuple.replace(tzinfo=None)
                except Exception:
                    email_record.received_at = datetime.utcnow()
            else:
                email_record.received_at = datetime.utcnow()

            # Optional retention per PRD Section 20
            if settings.RETAIN_EMAIL_BODIES:
                email_record.body_text = parsed.body_text
                email_record.body_html = parsed.body_html

            # Store attachment records
            for att in parsed.attachments:
                att_record = Attachment(
                    email_id=email_record.id,
                    gmail_attachment_id=att.gmail_attachment_id,
                    filename=att.filename,
                    mime_type=att.mime_type,
                    size=att.size,
                    status="PENDING",
                )
                db.add(att_record)
            db.commit()
            db.refresh(email_record)

            # 3. Format message for WhatsApp
            wa_text = MIMEParser.format_whatsapp_message(parsed)

            # 4. Dispatch text message(s) to WhatsApp
            logger.info(f"Forwarding email '{parsed.subject}' ({message_id}) to WhatsApp {recipient_number}...")
            send_results = await wa_service.send_text_message(
                to_number=recipient_number,
                text=wa_text,
            )

            # Record delivery logs for sent text parts
            for res in send_results:
                log_entry = DeliveryLog(
                    email_id=email_record.id,
                    whatsapp_message_id=res.get("whatsapp_message_id"),
                    recipient=recipient_number,
                    message_type="text",
                    status="sent",
                )
                db.add(log_entry)
            db.commit()

            # 5. Process Attachments if present
            all_att_succeeded = True
            att_warnings = []
            if email_record.attachments:
                all_att_succeeded, att_warnings = await attachment_service.process_email_attachments(
                    gmail_client=gmail_client,
                    email_record=email_record,
                    recipient_number=recipient_number,
                    whatsapp_svc=wa_service,
                    db=db,
                )

            # 6. Final State Evaluation
            if not all_att_succeeded:
                email_record.status = "PARTIAL"
                email_record.error_message = "; ".join(att_warnings)
            else:
                email_record.status = "SENT"
                email_record.error_message = None

            db.commit()
            logger.info(f"Email {message_id} successfully forwarded with status {email_record.status}")
            return True

        except Exception as exc:
            db.rollback()
            logger.error(f"Error processing email {message_id}: {exc}", exc_info=True)
            email_record.error_message = str(exc)

            is_transient = retry_service.is_transient_error(exc)
            can_retry, next_retry, delay_sec = retry_service.calculate_next_retry(email_record.retry_count)

            if is_transient and can_retry:
                email_record.status = "RETRY_WAIT"
                email_record.retry_count += 1
                email_record.next_retry_at = next_retry
                logger.warning(
                    f"Transient error on {message_id}. Scheduled retry #{email_record.retry_count} in {delay_sec}s"
                )
            else:
                email_record.status = "FAILED"
                logger.error(f"Permanent failure or retries exhausted for email {message_id}. Marked as FAILED.")

            db.commit()
            return False

    @classmethod
    async def retry_pending_emails(cls, db: Session, wa_service: Optional[WhatsAppService] = None) -> int:
        """
        Polls for emails in RETRY_WAIT whose next_retry_at <= now() and re-executes processing.
        """
        now = datetime.utcnow()
        pending = (
            db.query(Email)
            .filter(Email.status == "RETRY_WAIT", Email.next_retry_at <= now)
            .all()
        )

        if not pending:
            return 0

        wa_svc = wa_service or whatsapp_service
        retried_count = 0

        for email_record in pending:
            account = email_record.account
            if not account or not account.is_active:
                continue

            creds = GmailService.build_credentials(
                refresh_token_encrypted=account.refresh_token_ref,
                access_token=account.access_token,
                token_expiry=account.token_expiry,
            )
            gmail_client = GmailService.get_client(creds)

            logger.info(f"Retrying email {email_record.gmail_message_id} (attempt {email_record.retry_count})...")
            # Clear existing to re-run
            email_record.status = "PROCESSING"
            db.commit()

            success = await cls.process_single_message(
                gmail_client=gmail_client,
                account=account,
                message_id=email_record.gmail_message_id,
                db=db,
                wa_service=wa_svc,
            )
            if success:
                retried_count += 1

        return retried_count

    @classmethod
    async def reconcile_account(
        cls,
        account: GmailAccount,
        db: Session,
        wa_service: Optional[WhatsAppService] = None,
    ) -> int:
        """
        Reconciliation recovery job (FR-12 & PRD Section 22):
        Detects any emails missed due to Pub/Sub notification loss or service downtime.
        Queries recent messages from Gmail and processes any missing records.
        """
        logger.info(f"Starting reconciliation job for account: {account.email}")
        sync_run = SyncRun(
            account_id=account.id,
            history_start=account.history_id,
            status="RUNNING",
        )
        db.add(sync_run)
        db.commit()
        db.refresh(sync_run)

        wa_svc = wa_service or whatsapp_service
        creds = GmailService.build_credentials(
            refresh_token_encrypted=account.refresh_token_ref,
            access_token=account.access_token,
            token_expiry=account.token_expiry,
        )
        gmail_client = GmailService.get_client(creds)

        try:
            # Query recent messages from the inbox
            recent_ids = GmailService.list_recent_messages(service=gmail_client, query="newer_than:7d label:INBOX")
            sync_run.messages_discovered = len(recent_ids)

            processed = 0
            failed = 0

            for msg_id in recent_ids:
                # Check if already recorded
                exists = db.query(Email).filter(Email.gmail_message_id == msg_id).first()
                if exists:
                    continue  # already processed

                success = await cls.process_single_message(
                    gmail_client=gmail_client,
                    account=account,
                    message_id=msg_id,
                    db=db,
                    wa_service=wa_svc,
                )
                if success:
                    processed += 1
                else:
                    failed += 1

            sync_run.messages_processed = processed
            sync_run.messages_failed = failed
            sync_run.status = "SUCCESS"
            sync_run.completed_at = datetime.utcnow()
            db.commit()

            logger.info(
                f"Reconciliation completed for {account.email}: {processed} new processed, {failed} failed."
            )
            return processed

        except Exception as e:
            logger.error(f"Reconciliation failed for {account.email}: {e}", exc_info=True)
            sync_run.status = "FAILED"
            sync_run.error_details = str(e)
            sync_run.completed_at = datetime.utcnow()
            db.commit()
            return 0

    @classmethod
    def check_and_renew_watches(cls, db: Session) -> int:
        """
        Renews Gmail mailbox watches expiring within WATCH_RENEWAL_WINDOW_HOURS (Section 8).
        """
        renewal_threshold = datetime.utcnow() + timedelta(hours=settings.WATCH_RENEWAL_WINDOW_HOURS)
        accounts_to_renew = (
            db.query(GmailAccount)
            .filter(
                GmailAccount.is_active == True,
                (GmailAccount.watch_expiry == None) | (GmailAccount.watch_expiry <= renewal_threshold),
            )
            .all()
        )

        renewed_count = 0
        for account in accounts_to_renew:
            try:
                creds = GmailService.build_credentials(
                    refresh_token_encrypted=account.refresh_token_ref,
                    access_token=account.access_token,
                    token_expiry=account.token_expiry,
                )
                client = GmailService.get_client(creds)
                watch_res = GmailService.setup_watch(client)

                if "historyId" in watch_res and not account.history_id:
                    account.history_id = str(watch_res["historyId"])

                if "expiration" in watch_res:
                    exp_ms = int(watch_res["expiration"])
                    account.watch_expiry = datetime.utcfromtimestamp(exp_ms / 1000.0)
                else:
                    # Default 7 days if not provided
                    account.watch_expiry = datetime.utcnow() + timedelta(days=7)

                db.commit()
                renewed_count += 1
                logger.info(f"Renewed Gmail watch for {account.email}, expires at {account.watch_expiry}")
            except Exception as e:
                logger.error(f"Failed to renew Gmail watch for {account.email}: {e}")

        return renewed_count


sync_service = SyncService()
