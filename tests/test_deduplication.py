import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import IntegrityError
from app.models.email import Email
from app.services.sync_service import SyncService
from app.services.whatsapp_service import WhatsAppService


@pytest.mark.asyncio
async def test_deduplication_skips_existing_message(db_session, sample_account):
    msg_id = "gmail_msg_unique_001"

    # Pre-insert existing processed record
    existing = Email(
        account_id=sample_account.id,
        gmail_message_id=msg_id,
        status="SENT",
    )
    db_session.add(existing)
    db_session.commit()

    mock_client = MagicMock()
    mock_wa = MagicMock(spec=WhatsAppService)

    # Attempt to process duplicate message
    result = await SyncService.process_single_message(
        gmail_client=mock_client,
        account=sample_account,
        message_id=msg_id,
        db=db_session,
        wa_service=mock_wa,
    )

    # Must return False and not invoke Gmail or WhatsApp API
    assert result is False
    assert not mock_client.users().messages().get.called
    assert not mock_wa.send_text_message.called

    # Confirm only 1 record exists in the DB
    count = db_session.query(Email).filter(Email.gmail_message_id == msg_id).count()
    assert count == 1


def test_unique_constraint_enforcement(db_session, sample_account):
    email1 = Email(
        account_id=sample_account.id,
        gmail_message_id="duplicate_key_test",
        status="DISCOVERED",
    )
    db_session.add(email1)
    db_session.commit()

    email2 = Email(
        account_id=sample_account.id,
        gmail_message_id="duplicate_key_test",
        status="DISCOVERED",
    )
    db_session.add(email2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
