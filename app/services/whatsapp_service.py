import os
import json
import httpx
from typing import Any, Dict, List, Optional, Tuple
from app.config import settings
from app.services.mime_parser import MIMEParser
from app.utils.logging import logger


class WhatsAppService:
    """
    Client for Meta's WhatsApp Business Platform / Cloud API.
    Handles message dispatch, media uploads, and delivery status tracking.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        self.access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_version = api_version or settings.WHATSAPP_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"

    @property
    def is_configured(self) -> bool:
        """Checks if minimum credentials are configured and not dummy placeholders."""
        return bool(
            self.access_token
            and self.phone_number_id
            and self.access_token not in ["test-access-token", "your-meta-whatsapp-access-token"]
        )

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def send_text_message(
        self,
        to_number: str,
        text: str,
        preview_url: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Sends formatted text message(s) to a WhatsApp destination number.
        Splits automatically into clean chunks if text length > 4000 characters.
        Returns a list of sent message results (containing 'whatsapp_message_id').
        """
        clean_number = "".join(filter(str.isdigit, to_number))
        chunks = MIMEParser.chunk_whatsapp_message(text, max_chunk_len=4000)
        results = []

        if not self.is_configured:
            # Running in local / simulated mode
            logger.info(
                f"[SIMULATION] WhatsApp message dispatch to {clean_number} ({len(chunks)} chunks). Length: {len(text)}"
            )
            for idx, chunk in enumerate(chunks, 1):
                mock_msg_id = f"wamid.SIMULATED_{idx}_{hash(chunk) & 0xffffffff}"
                results.append({
                    "whatsapp_message_id": mock_msg_id,
                    "status": "sent",
                    "part": idx,
                    "total_parts": len(chunks),
                })
            return results

        async with httpx.AsyncClient(timeout=30.0) as client:
            for idx, chunk in enumerate(chunks, 1):
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": clean_number,
                    "type": "text",
                    "text": {
                        "body": chunk,
                        "preview_url": preview_url,
                    },
                }

                endpoint = f"{self.base_url}/messages"
                response = await client.post(endpoint, json=payload, headers=self._get_headers())

                if response.status_code == 429:
                    raise httpx.HTTPStatusError(
                        f"WhatsApp Cloud API rate limited (429): {response.text}",
                        request=response.request,
                        response=response,
                    )

                if response.is_error:
                    logger.error(f"WhatsApp Cloud API error ({response.status_code}): {response.text}")
                    raise httpx.HTTPStatusError(
                        f"WhatsApp Cloud API returned {response.status_code}: {response.text}",
                        request=response.request,
                        response=response,
                    )

                resp_data = response.json()
                msg_id = None
                if "messages" in resp_data and resp_data["messages"]:
                    msg_id = resp_data["messages"][0].get("id")

                results.append({
                    "whatsapp_message_id": msg_id or f"wamid.UNKNOWN_{idx}",
                    "status": "sent",
                    "part": idx,
                    "total_parts": len(chunks),
                })

        return results

    async def upload_media(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> str:
        """
        Uploads media bytes to Meta's WhatsApp Cloud API media endpoint.
        Returns the created media_id.
        """
        if not self.is_configured:
            mock_id = f"mock_media_id_{hash(filename) & 0xffffffff}"
            logger.info(f"[SIMULATION] Uploaded media {filename} ({len(file_bytes)} bytes) -> id={mock_id}")
            return mock_id

        endpoint = f"{self.base_url}/media"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {
            "messaging_product": "whatsapp",
            "type": mime_type,
        }
        files = {
            "file": (filename, file_bytes, mime_type),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, data=data, files=files, headers=headers)
            if response.status_code == 429:
                raise httpx.HTTPStatusError(
                    f"WhatsApp Media upload rate limited (429): {response.text}",
                    request=response.request,
                    response=response,
                )
            if response.is_error:
                logger.error(f"WhatsApp media upload failed ({response.status_code}): {response.text}")
                raise httpx.HTTPStatusError(
                    f"Media upload failed: {response.text}",
                    request=response.request,
                    response=response,
                )
            return response.json().get("id", "")

    async def send_media_message(
        self,
        to_number: str,
        media_id: str,
        mime_type: str,
        filename: str,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sends an uploaded media item (document, image, video, or audio) to recipient.
        """
        clean_number = "".join(filter(str.isdigit, to_number))
        
        # Determine WhatsApp media message type
        if mime_type.startswith("image/"):
            wa_type = "image"
        elif mime_type.startswith("audio/"):
            wa_type = "audio"
        elif mime_type.startswith("video/"):
            wa_type = "video"
        else:
            wa_type = "document"

        if not self.is_configured:
            mock_msg_id = f"wamid.SIMULATED_MEDIA_{hash(media_id) & 0xffffffff}"
            logger.info(
                f"[SIMULATION] Sent {wa_type} '{filename}' (media_id={media_id}) to {clean_number}"
            )
            return {
                "whatsapp_message_id": mock_msg_id,
                "status": "sent",
                "media_type": wa_type,
            }

        media_payload: Dict[str, Any] = {"id": media_id}
        if wa_type == "document":
            media_payload["filename"] = filename
            if caption:
                media_payload["caption"] = caption
        elif wa_type in ["image", "video"] and caption:
            media_payload["caption"] = caption

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_number,
            "type": wa_type,
            wa_type: media_payload,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            endpoint = f"{self.base_url}/messages"
            response = await client.post(endpoint, json=payload, headers=self._get_headers())
            
            if response.is_error:
                logger.error(f"WhatsApp send_media failed ({response.status_code}): {response.text}")
                raise httpx.HTTPStatusError(
                    f"WhatsApp send_media failed: {response.text}",
                    request=response.request,
                    response=response,
                )
            
            resp_data = response.json()
            msg_id = None
            if "messages" in resp_data and resp_data["messages"]:
                msg_id = resp_data["messages"][0].get("id")

            return {
                "whatsapp_message_id": msg_id or f"wamid.UNKNOWN_{media_id}",
                "status": "sent",
                "media_type": wa_type,
            }


whatsapp_service = WhatsAppService()
