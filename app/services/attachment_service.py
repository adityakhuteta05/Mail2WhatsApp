from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.config import settings
from app.models.attachment import Attachment
from app.models.email import Email
from app.services.gmail_service import GmailService
from app.services.whatsapp_service import WhatsAppService
from app.utils.logging import logger

# Meta Cloud API media size limits
MAX_IMAGE_BYTES = 5 * 1024 * 1024       # 5 MB
MAX_DOCUMENT_BYTES = 100 * 1024 * 1024  # 100 MB


class AttachmentService:
    """
    Handles downloading attachments from Gmail, validating size and format,
    uploading to WhatsApp Cloud API, and dispatching media messages.
    """

    @classmethod
    async def process_email_attachments(
        cls,
        gmail_client,
        email_record: Email,
        recipient_number: str,
        whatsapp_svc: WhatsAppService,
        db: Session,
    ) -> Tuple[bool, List[str]]:
        """
        Processes all attachments associated with an email record.
        Returns: (all_succeeded: bool, list_of_warning_messages)
        """
        all_succeeded = True
        warnings = []

        max_app_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024

        for attachment in email_record.attachments:
            try:
                # 1. Size pre-validation
                limit = MAX_IMAGE_BYTES if attachment.mime_type.startswith("image/") else MAX_DOCUMENT_BYTES
                effective_limit = min(limit, max_app_bytes)

                if attachment.size > effective_limit:
                    warning = (
                        f"Attachment '{attachment.filename}' ({attachment.size // 1024} KB) "
                        f"exceeds size limit ({effective_limit // 1024} KB). Skipped."
                    )
                    logger.warning(warning)
                    attachment.status = "SKIPPED"
                    attachment.error_message = warning
                    db.commit()
                    warnings.append(warning)
                    all_succeeded = False
                    continue

                # 2. Fetch raw attachment bytes from Gmail
                logger.info(f"Downloading attachment '{attachment.filename}' from Gmail...")
                file_bytes = GmailService.get_attachment_bytes(
                    service=gmail_client,
                    message_id=email_record.gmail_message_id,
                    attachment_id=attachment.gmail_attachment_id,
                )

                # 3. Upload to Meta WhatsApp media endpoint
                logger.info(f"Uploading '{attachment.filename}' to WhatsApp media API...")
                media_id = await whatsapp_svc.upload_media(
                    file_bytes=file_bytes,
                    filename=attachment.filename,
                    mime_type=attachment.mime_type,
                )

                attachment.whatsapp_media_id = media_id
                attachment.status = "UPLOADED"
                db.commit()

                # 4. Dispatch media message
                caption = f"📎 {attachment.filename}"
                logger.info(f"Sending media message for '{attachment.filename}'...")
                send_result = await whatsapp_svc.send_media_message(
                    to_number=recipient_number,
                    media_id=media_id,
                    mime_type=attachment.mime_type,
                    filename=attachment.filename,
                    caption=caption,
                )

                attachment.status = "SENT"
                db.commit()

            except Exception as e:
                logger.error(f"Failed to process attachment '{attachment.filename}': {e}", exc_info=True)
                attachment.status = "FAILED"
                attachment.error_message = str(e)
                db.commit()
                warnings.append(f"Failed to deliver attachment '{attachment.filename}': {str(e)}")
                all_succeeded = False

        return all_succeeded, warnings


attachment_service = AttachmentService()
