import base64
import pytest
from app.services.mime_parser import MIMEParser
from app.schemas.email import ParsedEmail, AttachmentSchema


def test_html_to_whatsapp_text_formatting():
    html = """
    <html>
      <head><style>body { font-size: 14px; }</style></head>
      <body>
        <h1>Important Notice</h1>
        <p>This is <b>bold text</b> and this is <i>italic text</i> and <s>strikethrough</s>.</p>
        <p>Check out our <a href="https://example.com">Website</a> for details.</p>
        <ul>
          <li>Point number one</li>
          <li>Point number two</li>
        </ul>
        <pre><code>x = 10 + 20</code></pre>
      </body>
    </html>
    """
    result = MIMEParser.html_to_whatsapp_text(html)
    assert "*Important Notice*" in result
    assert "*bold text*" in result
    assert "_italic text_" in result
    assert "~strikethrough~" in result
    assert "Website (https://example.com)" in result
    assert "• Point number one" in result
    assert "• Point number two" in result
    assert "x = 10 + 20" in result
    # Check styles are stripped
    assert "font-size" not in result


def test_decode_mime_header():
    # Encoded RFC 2047 string: "Hello World" in base64 is SGVsbG8gV29ybGQ=
    encoded = "=?UTF-8?B?SGVsbG8gV29ybGQ=?="
    decoded = MIMEParser.decode_mime_header(encoded)
    assert decoded == "Hello World"

    plain = "Regular Subject Line"
    assert MIMEParser.decode_mime_header(plain) == "Regular Subject Line"
    assert MIMEParser.decode_mime_header(None) == ""


def test_parse_gmail_api_message_plain():
    body_content = "Hello, this is a plain text email message."
    b64_data = base64.urlsafe_b64encode(body_content.encode("utf-8")).decode("utf-8")

    message_dict = {
        "id": "189abc12345",
        "threadId": "thread_999",
        "snippet": "Hello, this is a plain...",
        "payload": {
            "headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "To", "value": "Bob <bob@example.com>"},
                {"name": "Subject", "value": "Project Update"},
                {"name": "Date", "value": "Tue, 23 Sep 2026 10:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {
                "data": b64_data,
                "size": len(body_content),
            },
        },
    }

    parsed = MIMEParser.parse_gmail_api_message(message_dict)
    assert parsed.gmail_message_id == "189abc12345"
    assert parsed.sender == "Alice <alice@example.com>"
    assert parsed.recipients == "Bob <bob@example.com>"
    assert parsed.subject == "Project Update"
    assert parsed.body_text == body_content
    assert parsed.has_html_fallback is False
    assert len(parsed.attachments) == 0


def test_parse_gmail_api_message_multipart_with_attachment():
    plain_text = "Please check attached document."
    plain_b64 = base64.urlsafe_b64encode(plain_text.encode("utf-8")).decode("utf-8")

    message_dict = {
        "id": "msg_with_att_01",
        "threadId": "thread_att_01",
        "payload": {
            "headers": [
                {"name": "From", "value": "Manager <boss@example.com>"},
                {"name": "Subject", "value": "Quarterly Report"},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": plain_b64},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "q3_report.pdf",
                    "body": {
                        "attachmentId": "att_pdf_12345",
                        "size": 1048576,  # 1MB
                    },
                },
            ],
        },
    }

    parsed = MIMEParser.parse_gmail_api_message(message_dict)
    assert parsed.gmail_message_id == "msg_with_att_01"
    assert parsed.body_text == plain_text
    assert len(parsed.attachments) == 1
    assert parsed.attachments[0].filename == "q3_report.pdf"
    assert parsed.attachments[0].mime_type == "application/pdf"
    assert parsed.attachments[0].gmail_attachment_id == "att_pdf_12345"


def test_format_whatsapp_message():
    parsed = ParsedEmail(
        gmail_message_id="msg123",
        sender="Rahul Sharma <rahul@example.com>",
        recipients="Aditya <user@example.com>",
        subject="Project Meeting",
        date="23 Sep 2026, 11:45 AM",
        body_text="Hi Aditya,\n\nThe meeting is scheduled for tomorrow at 10:00 AM.\n\nRegards,\nRahul",
        attachments=[
            AttachmentSchema(
                gmail_attachment_id="att1",
                filename="project_report.pdf",
                mime_type="application/pdf",
                size=204800,  # 200 KB
            )
        ],
    )

    formatted = MIMEParser.format_whatsapp_message(parsed)
    assert "*NEW EMAIL*" in formatted
    assert "*From:* Rahul Sharma <rahul@example.com>" in formatted
    assert "*To:* Aditya <user@example.com>" in formatted
    assert "*Subject:* Project Meeting" in formatted
    assert "*Date:* 23 Sep 2026, 11:45 AM" in formatted
    assert "━━━━━━━━━━━━━━━━━━━━━━" in formatted
    assert "The meeting is scheduled for tomorrow" in formatted
    assert "*📎 Attachments:*" in formatted
    assert "• project_report.pdf (200 KB)" in formatted


def test_chunk_whatsapp_message():
    # Short message does not chunk
    short = "This is a short message."
    chunks = MIMEParser.chunk_whatsapp_message(short, max_chunk_len=100)
    assert len(chunks) == 1
    assert chunks[0] == short

    # Long message exceeds max_chunk_len
    para1 = "Paragraph 1: " + ("A" * 60)
    para2 = "Paragraph 2: " + ("B" * 60)
    long_msg = f"{para1}\n\n{para2}"

    chunks = MIMEParser.chunk_whatsapp_message(long_msg, max_chunk_len=80)
    assert len(chunks) == 2
    assert "*(Part 1/2)*" in chunks[0]
    assert "*(Part 2/2)*" in chunks[1]
