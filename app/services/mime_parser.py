import base64
import email
from email.header import decode_header
import re
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup, NavigableString, Tag
from app.schemas.email import AttachmentSchema, ParsedEmail
from app.utils.logging import logger


class MIMEParser:
    """
    Parses Gmail message payloads or raw MIME data, extracts metadata,
    body (preferring text/plain, or converting HTML to WhatsApp format),
    and attachments according to PRD Section 12.
    """

    @classmethod
    def decode_mime_header(cls, header_value: Optional[str]) -> str:
        """Decodes RFC 2047 encoded header strings (e.g. =?utf-8?B?...?=)."""
        if not header_value:
            return ""
        decoded_fragments = []
        try:
            for text, charset in decode_header(header_value):
                if isinstance(text, bytes):
                    encoding = charset or "utf-8"
                    try:
                        decoded_fragments.append(text.decode(encoding, errors="replace"))
                    except (LookupError, UnicodeDecodeError):
                        decoded_fragments.append(text.decode("utf-8", errors="replace"))
                else:
                    decoded_fragments.append(str(text))
            return "".join(decoded_fragments)
        except Exception as e:
            logger.warning(f"Failed to decode MIME header '{header_value}': {e}")
            return str(header_value)

    @classmethod
    def html_to_whatsapp_text(cls, html_content: str) -> str:
        """
        Converts HTML to clean, semantic WhatsApp-formatted text.
        Converts <b>/<strong> -> *bold*, <i>/<em> -> _italic_, <s>/<del> -> ~strike~,
        <code>/<pre> -> ```code```, <a> -> text (url), <h1>-<h6> -> *Header*,
        <li> -> • item, <p>/<br> -> newlines.
        """
        if not html_content or not html_content.strip():
            return ""

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements completely
        for tag in soup(["script", "style", "head", "meta", "noscript", "svg"]):
            tag.decompose()

        def process_element(elem) -> str:
            if isinstance(elem, NavigableString):
                return str(elem)
            if not isinstance(elem, Tag):
                return ""

            name = elem.name.lower()
            inner = "".join(process_element(child) for child in elem.children)

            if name in ["b", "strong"]:
                inner_stripped = inner.strip()
                return f" *{inner_stripped}* " if inner_stripped else ""
            elif name in ["i", "em"]:
                inner_stripped = inner.strip()
                return f" _{inner_stripped}_ " if inner_stripped else ""
            elif name in ["s", "strike", "del"]:
                inner_stripped = inner.strip()
                return f" ~{inner_stripped}~ " if inner_stripped else ""
            elif name in ["code"]:
                inner_stripped = inner.strip()
                return f" ```{inner_stripped}``` " if inner_stripped else ""
            elif name in ["pre"]:
                return f"\n```{inner.strip()}```\n"
            elif name in ["a"]:
                href = elem.get("href", "").strip()
                text = inner.strip()
                if not href:
                    return text
                if not text or text == href:
                    return f" {href} "
                return f" {text} ({href}) "
            elif name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                inner_stripped = inner.strip()
                return f"\n\n*{inner_stripped}*\n" if inner_stripped else ""
            elif name == "li":
                return f"\n• {inner.strip()}"
            elif name in ["p", "div"]:
                return f"\n\n{inner.strip()}\n" if inner.strip() else "\n"
            elif name == "br":
                return "\n"
            elif name == "hr":
                return "\n━━━━━━━━━━━━━━━━━━━━━━\n"
            elif name in ["blockquote"]:
                lines = inner.strip().split("\n")
                return "\n" + "\n".join(f"> {line}" for line in lines) + "\n"
            elif name == "img":
                alt = elem.get("alt", "").strip()
                src = elem.get("src", "").strip()
                if alt:
                    return f" [Image: {alt}] "
                elif src and not src.startswith("data:"):
                    return f" [Image: {src}] "
                return " [Image] "
            else:
                return inner

        formatted = process_element(soup)
        # Normalize excessive blank lines while preserving meaningful paragraph breaks
        cleaned = re.sub(r'\n{3,}', '\n\n', formatted)
        # Normalize multiple inline spaces
        cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
        return cleaned.strip()

    @classmethod
    def _decode_body_data(cls, data_str: str) -> str:
        """Decodes URL-safe base64 string from Gmail message body part."""
        if not data_str:
            return ""
        # Fix padding if necessary
        padded = data_str + "=" * ((4 - len(data_str) % 4) % 4)
        raw_bytes = base64.urlsafe_b64decode(padded.encode("utf-8"))
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return raw_bytes.decode("latin-1", errors="replace")

    @classmethod
    def parse_gmail_api_message(cls, message_dict: Dict[str, Any]) -> ParsedEmail:
        """
        Parses a message object returned by Gmail API users.messages.get(format='full').
        Extracts headers, finds plain text or HTML fallback, and locates attachments.
        """
        msg_id = message_dict.get("id", "")
        thread_id = message_dict.get("threadId", "")
        payload = message_dict.get("payload", {})
        headers_list = payload.get("headers", [])

        # Extract headers into a dict
        headers: Dict[str, str] = {}
        for h in headers_list:
            headers[h.get("name", "").lower()] = h.get("value", "")

        sender = cls.decode_mime_header(headers.get("from", "Unknown Sender"))
        recipients = cls.decode_mime_header(headers.get("to", ""))
        cc = cls.decode_mime_header(headers.get("cc", ""))
        if cc:
            recipients = f"{recipients}, CC: {cc}" if recipients else f"CC: {cc}"
        
        subject = cls.decode_mime_header(headers.get("subject", "(No Subject)"))
        date_str = headers.get("date", "")

        # Walk parts to extract body and attachments
        plain_parts: List[str] = []
        html_parts: List[str] = []
        attachments: List[AttachmentSchema] = []

        def walk_parts(part: Dict[str, Any]):
            mime_type = part.get("mimeType", "")
            filename = part.get("filename", "")
            body = part.get("body", {})
            attachment_id = body.get("attachmentId")
            data = body.get("data")

            # Check if this part is an attachment
            if attachment_id or (filename and mime_type not in ["text/plain", "text/html"]):
                size = body.get("size", 0)
                attachments.append(
                    AttachmentSchema(
                        gmail_attachment_id=attachment_id or f"inline-{msg_id}-{filename}",
                        filename=filename or "attachment",
                        mime_type=mime_type or "application/octet-stream",
                        size=size,
                        status="PENDING",
                    )
                )
                return

            if mime_type == "text/plain" and data:
                text_content = cls._decode_body_data(data)
                plain_parts.append(text_content)
            elif mime_type == "text/html" and data:
                html_content = cls._decode_body_data(data)
                html_parts.append(html_content)

            # Recurse for nested multipart (multipart/mixed, multipart/alternative, etc.)
            sub_parts = part.get("parts", [])
            for sub in sub_parts:
                walk_parts(sub)

        walk_parts(payload)

        # Decide body text: Prefer plain text; fallback to converted HTML
        body_html = None
        has_html_fallback = False

        if plain_parts:
            body_text = "\n".join(plain_parts).strip()
            if html_parts:
                body_html = "\n".join(html_parts)
        elif html_parts:
            body_html = "\n".join(html_parts)
            body_text = cls.html_to_whatsapp_text(body_html)
            has_html_fallback = True
        else:
            # Fallback to snippet from Gmail payload if neither was present
            body_text = message_dict.get("snippet", "")

        return ParsedEmail(
            gmail_message_id=msg_id,
            thread_id=thread_id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            date=date_str,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
            has_html_fallback=has_html_fallback,
        )

    @classmethod
    def format_whatsapp_message(cls, email_data: ParsedEmail) -> str:
        """
        Formats parsed email data into the WhatsApp presentation specified in PRD Section 12.
        Example:
        *NEW EMAIL*
        *From:* Rahul Sharma <rahul@example.com>
        *To:* Aditya <user@example.com>
        *Subject:* Project Meeting
        *Date:* 23 Sep 2026, 11:45 AM
        ━━━━━━━━━━━━━━━━━━━━━━
        Hi Aditya,
        ...
        *📎 Attachments:*
        • project_report.pdf
        """
        header_lines = [
            "*NEW EMAIL*",
            f"*From:* {email_data.sender}",
        ]
        if email_data.recipients:
            header_lines.append(f"*To:* {email_data.recipients}")
        header_lines.append(f"*Subject:* {email_data.subject}")
        if email_data.date:
            header_lines.append(f"*Date:* {email_data.date}")
        
        header_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        
        body_section = email_data.body_text.strip() if email_data.body_text else "_(No text content)_"
        
        attachment_section = ""
        if email_data.attachments:
            attachment_lines = ["\n*📎 Attachments:*"]
            for att in email_data.attachments:
                size_str = f" ({att.size // 1024} KB)" if att.size > 0 else ""
                attachment_lines.append(f"• {att.filename}{size_str}")
            attachment_section = "\n".join(attachment_lines)

        full_message = "\n".join(header_lines) + "\n\n" + body_section
        if attachment_section:
            full_message += "\n" + attachment_section

        return full_message

    @classmethod
    def chunk_whatsapp_message(cls, text: str, max_chunk_len: int = 4000) -> List[str]:
        """
        Splits a text message into chunks smaller than max_chunk_len (WhatsApp limit is 4096).
        Splits on paragraph breaks or line breaks cleanly, and prefixes (Part X/Y) if multi-part.
        """
        if len(text) <= max_chunk_len:
            return [text]

        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            # If paragraph itself is longer than max_chunk_len, split by line
            if len(para) > max_chunk_len:
                lines = para.split("\n")
                for line in lines:
                    if len(line) > max_chunk_len:
                        # Split by words
                        words = line.split(" ")
                        for word in words:
                            if len(current_chunk) + len(word) + 1 > max_chunk_len:
                                if current_chunk:
                                    chunks.append(current_chunk.strip())
                                current_chunk = word + " "
                            else:
                                current_chunk += word + " "
                    else:
                        if len(current_chunk) + len(line) + 1 > max_chunk_len:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = line + "\n"
                        else:
                            current_chunk += line + "\n"
            else:
                candidate = f"{current_chunk}\n\n{para}" if current_chunk else para
                if len(candidate) > max_chunk_len:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = para
                else:
                    current_chunk = candidate

        if current_chunk and current_chunk.strip():
            chunks.append(current_chunk.strip())

        # If multiple chunks, add header (Part X of Y)
        total_parts = len(chunks)
        if total_parts > 1:
            numbered_chunks = []
            for i, chunk in enumerate(chunks, 1):
                part_header = f"*(Part {i}/{total_parts})*\n"
                numbered_chunks.append(part_header + chunk)
            return numbered_chunks

        return chunks
