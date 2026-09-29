import base64
import json
import pytest
from unittest.mock import AsyncMock, patch
from app.schemas.webhook import PubSubMessage, PubSubPushRequest
from app.services.pubsub_service import PubSubService


def test_pubsub_service_decode_valid():
    inner_data = {
        "emailAddress": "user@example.com",
        "historyId": "987654",
    }
    b64_str = base64.b64encode(json.dumps(inner_data).encode("utf-8")).decode("utf-8")
    push_req = PubSubPushRequest(
        message=PubSubMessage(data=b64_str, messageId="pubsub_msg_01")
    )

    result = PubSubService.decode_push_notification(push_req)
    assert result.emailAddress == "user@example.com"
    assert result.historyId == "987654"


def test_pubsub_service_decode_invalid_json():
    bad_b64 = base64.b64encode(b"not-json-content").decode("utf-8")
    push_req = PubSubPushRequest(
        message=PubSubMessage(data=bad_b64, messageId="pubsub_msg_bad")
    )

    with pytest.raises(ValueError, match="Malformed Pub/Sub data encoding"):
        PubSubService.decode_push_notification(push_req)


def test_pubsub_service_missing_fields():
    data = {"emailAddress": "user@example.com"}  # missing historyId
    b64_str = base64.b64encode(json.dumps(data).encode("utf-8")).decode("utf-8")
    push_req = PubSubPushRequest(message=PubSubMessage(data=b64_str))

    with pytest.raises(ValueError, match="Missing required fields"):
        PubSubService.decode_push_notification(push_req)


@patch("app.routes.webhook.SyncService.process_mailbox_notification", new_callable=AsyncMock)
def test_pubsub_endpoint_success(mock_process, client, sample_account):
    mock_process.return_value = 1

    inner_data = {
        "emailAddress": sample_account.email,
        "historyId": "1001",
    }
    b64_str = base64.b64encode(json.dumps(inner_data).encode("utf-8")).decode("utf-8")

    payload = {
        "message": {
            "data": b64_str,
            "messageId": "pubsub_111",
            "publishTime": "2026-09-29T10:00:00Z",
        },
        "subscription": "projects/test/subscriptions/sub-1",
    }

    # Pass the verification token configured in conftest / env
    headers = {"X-Pubsub-Token": "test-pubsub-token"}
    response = client.post("/webhook/google-pubsub", json=payload, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "acknowledged"
    assert res_data["processed"] == 1
    mock_process.assert_awaited_once()


def test_pubsub_endpoint_unauthorized(client):
    payload = {
        "message": {
            "data": "eyJlbWFpbEFkZHJlc3MiOiAieEB5LmNvbSIsICJoaXN0b3J5SWQiOiAiMSJ9",
        }
    }
    # Bad token returns 403
    response = client.post("/webhook/google-pubsub", json=payload, headers={"X-Pubsub-Token": "bad-token"})
    assert response.status_code == 403
