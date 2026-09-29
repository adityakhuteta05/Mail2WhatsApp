import pytest
from app.services.whatsapp_service import WhatsAppService


@pytest.mark.asyncio
async def test_whatsapp_service_simulation_mode():
    # Service with mock/simulation credentials
    wa = WhatsAppService(access_token="test-access-token", phone_number_id="100000000")
    assert wa.is_configured is False  # Recognized as simulation mode

    results = await wa.send_text_message(
        to_number="+1 (555) 123-4567",
        text="Hello from simulation test!",
    )
    assert len(results) == 1
    assert results[0]["status"] == "sent"
    assert "wamid.SIMULATED_" in results[0]["whatsapp_message_id"]


@pytest.mark.asyncio
async def test_whatsapp_service_media_simulation():
    wa = WhatsAppService(access_token="test-access-token", phone_number_id="100000000")
    media_id = await wa.upload_media(
        file_bytes=b"%PDF-1.4 mock content",
        filename="invoice.pdf",
        mime_type="application/pdf",
    )
    assert "mock_media_id_" in media_id

    send_res = await wa.send_media_message(
        to_number="15551234567",
        media_id=media_id,
        mime_type="application/pdf",
        filename="invoice.pdf",
        caption="Your Invoice",
    )
    assert send_res["status"] == "sent"
    assert send_res["media_type"] == "document"
    assert "wamid.SIMULATED_MEDIA_" in send_res["whatsapp_message_id"]
