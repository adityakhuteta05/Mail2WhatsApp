import logging
import re
import sys
from app.config import settings

# Patterns for sensitive data that must be redacted in logs
SENSITIVE_PATTERNS = [
    (re.compile(r'(Bearer\s+)[A-Za-z0-9_\-\.]{15,}', re.IGNORECASE), r'\1[REDACTED_TOKEN]'),
    (re.compile(r'(access_token=)[^&\s]+', re.IGNORECASE), r'\1[REDACTED_TOKEN]'),
    (re.compile(r'(refresh_token=)[^&\s]+', re.IGNORECASE), r'\1[REDACTED_TOKEN]'),
    (re.compile(r'(client_secret=)[^&\s]+', re.IGNORECASE), r'\1[REDACTED_SECRET]'),
    (re.compile(r'("access_token"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1[REDACTED_TOKEN]\2'),
    (re.compile(r'("refresh_token"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1[REDACTED_TOKEN]\2'),
    (re.compile(r'("client_secret"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1[REDACTED_SECRET]\2'),
]


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs tokens, secrets, and auth credentials from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.sanitize(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.sanitize(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.sanitize(str(a)) for a in record.args)
        return True

    @staticmethod
    def sanitize(text: str) -> str:
        sanitized = text
        for pattern, replacement in SENSITIVE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized


def setup_logging():
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger("mail2whatsapp")
    logger.setLevel(log_level)

    # Avoid duplicate handlers on reload
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)

    return logger


logger = setup_logging()
