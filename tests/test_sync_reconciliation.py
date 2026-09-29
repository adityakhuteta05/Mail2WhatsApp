import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from googleapiclient.errors import HttpError
import httpx

from app.models.delivery import DeliveryLog
from app.models.email import Email
from app.services.sync_service import SyncService
from app.services.whatsapp_service import WhatsAppService


@pytest.mark.asyncio
async def test_end_to_end_single_message_processing(db_session, sample_account):
    msg_id = "test_msg_e2e_001"
    body_text = "Hello! This is a test email message."
    b64_body = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("utf-8")

    mock_msg_payload = {
        "id": msg_id,
        "threadId": "thread_e2e",
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "To", "value": "Recipient <recipient@example.com>"},
                {"name": "Subject", "value": "Important Update"},
                {"name": "Date", "value": "Tue, 23 Sep 2026 12:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": b64_body},
        },
    }

    mock_gmail_client = MagicMock()
    mock_gmail_client.users().messages().get().execute.return_value = mock_msg_payload

    mock_wa_svc = MagicMock(spec=WhatsAppService)
    mock_wa_svc.send_text_message = AsyncMock(return_value=[
        {"whatsapp_message_id": "wamid.TEST_E2E_123", "status": "sent"}
    ])

    success = await SyncService.process_single_message(
        gmail_client=mock_gmail_client,
        account=sample_account,
        message_id=msg_id,
        db=db_session,
        wa_service=mock_wa_svc,
    )

    assert success is True

    # Verify DB record
    email_rec = db_session.query(Email).filter(Email.gmail_message_id == msg_id).first()
    assert email_rec is not None
    assert email_rec.status == "SENT"
    assert email_rec.subject == "Important Update"
    assert email_rec.sender == "Sender <sender@example.com>"

    # Verify delivery log
    d_log = db_session.query(DeliveryLog).filter(DeliveryLog.email_id == email_rec.id).first()
    assert d_log is not None
    assert d_log.whatsapp_message_id == "wamid.TEST_E2E_123"
    assert d_log.status == "sent"


@pytest.mark.asyncio
async def test_reconciliation_fallback_on_expired_history(db_session, sample_account):
    resp_mock = MagicMock()
    resp_mock.status = 404
    http_error_404 = HttpError(resp=resp_mock, content=b"History ID not found")

    with patch("app.services.gmail_service.GmailService.get_history_changes", side_effect=http_error_404):
        with patch.object(SyncService, "reconcile_account", new_callable=AsyncMock) as mock_reconcile:
            mock_reconcile.return_value = 2

            count = await SyncService.process_mailbox_notification(
                email_address=sample_account.email,
                incoming_history_id="999999",
                db=db_session,
            )

            assert count == 2
            mock_reconcile.assert_awaited_once()


def test_whatsapp_delivery_webhook_status_update(client, db_session, sample_account):
    # Pre-create email and delivery log
    email_rec = Email(
        account_id=sample_account.id,
        gmail_message_id="msg_delivery_test",
        status="SENT",
    )
    db_session.add(email_rec)
    db_session.commit()

    log_rec = DeliveryLog(
        email_id=email_rec.id,
        whatsapp_message_id="wamid.STATUS_TEST_999",
        recipient="15551234567",
        status="sent",
    )
    db_session.add(log_rec)
    db_session.commit()

    # Incoming Meta WhatsApp webhook status update
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "wa_business_account_id",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": "wamid.STATUS_TEST_999",
                                    "status": "delivered",
                                    "timestamp": "1727000000",
                                    "recipient_id": "15551234567",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    response = client.post("/webhook/whatsapp", json=webhook_payload)
    assert response.status_code == 200
    assert response.json()["updated"] == 1

    db_session.refresh(log_rec)
    db_session.refresh(email_rec)
    assert log_rec.status == "delivered"
    assert email_rec.status == "DELIVERED"
