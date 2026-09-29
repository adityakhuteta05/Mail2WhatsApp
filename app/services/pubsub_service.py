import base64
import json
from typing import Any, Dict, Optional, Tuple
from app.schemas.webhook import GmailPubSubData, PubSubPushRequest
from app.utils.logging import logger


class PubSubService:
    """
    Parses and decodes Google Cloud Pub/Sub push messages containing
    Gmail mailbox change notifications.
    """

    @classmethod
    def decode_push_notification(cls, request_payload: PubSubPushRequest) -> GmailPubSubData:
        """
        Extracts base64 message data and decodes JSON into GmailPubSubData.
        Payload format from Gmail:
        {
          "emailAddress": "user@example.com",
          "historyId": "1234567"
        }
        """
        raw_b64 = request_payload.message.data
        if not raw_b64:
            raise ValueError("Pub/Sub message data field is empty")

        try:
            # Fix base64 padding if needed
            padded = raw_b64 + "=" * ((4 - len(raw_b64) % 4) % 4)
            decoded_bytes = base64.b64decode(padded)
            decoded_str = decoded_bytes.decode("utf-8")
            data_dict = json.loads(decoded_str)
        except Exception as e:
            logger.error(f"Failed to decode Pub/Sub base64 payload: {e}")
            raise ValueError(f"Malformed Pub/Sub data encoding: {e}")

        email_address = data_dict.get("emailAddress")
        history_id = str(data_dict.get("historyId", ""))

        if not email_address or not history_id:
            raise ValueError(f"Missing required fields in Pub/Sub data: {data_dict}")

        return GmailPubSubData(emailAddress=email_address, historyId=history_id)


pubsub_service = PubSubService()
