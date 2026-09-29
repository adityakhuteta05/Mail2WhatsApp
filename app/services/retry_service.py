import random
from datetime import datetime, timedelta
from typing import Optional, Tuple
import httpx
from googleapiclient.errors import HttpError
from app.utils.logging import logger

# Recommended backoff in seconds (PRD Section 21)
# attempt 1: immediate (0s)
# attempt 2: ~5s
# attempt 3: ~30s
# attempt 4: ~120s (2m)
# attempt 5: ~600s (10m)
BACKOFF_DELAYS = [0, 5, 30, 120, 600]
MAX_RETRY_ATTEMPTS = len(BACKOFF_DELAYS)


class RetryService:
    """
    Manages retry schedules, error classification (transient vs permanent),
    and exponential backoff calculations with jitter.
    """

    @classmethod
    def is_transient_error(cls, exc: Exception) -> bool:
        """
        Determines whether an exception is transient (network timeout, rate limit 429,
        server error 5xx) or permanent (invalid payload 400, unauthorized 401, not found 404).
        """
        # HTTP client errors (httpx)
        if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.NetworkError)):
            return True

        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in (429, 500, 502, 503, 504):
                return True
            # Meta WhatsApp Cloud API returns HTTP 400 for rate limit errors like 131056
            try:
                data = exc.response.json()
                err_code = data.get("error", {}).get("code")
                err_msg = str(data.get("error", {}).get("message", "")).lower()
                if err_code in (131056, 131048, 130429) or "rate limit" in err_msg:
                    return True
            except Exception:
                pass
            return False

        # Google API HTTP errors
        if isinstance(exc, HttpError):
            status = exc.resp.status
            if status in (429, 500, 502, 503, 504):
                return True
            return False

        # Generic network / socket errors
        error_str = str(exc).lower()
        if any(term in error_str for term in ["connection reset", "connection refused", "timeout", "timed out"]):
            return True

        return False

    @classmethod
    def calculate_next_retry(cls, current_retry_count: int) -> Tuple[bool, Optional[datetime], int]:
        """
        Calculates the next retry timestamp using bounded backoff + jitter.
        Returns: (can_retry: bool, next_retry_timestamp: Optional[datetime], delay_seconds: int)
        """
        next_attempt = current_retry_count + 1
        if next_attempt > MAX_RETRY_ATTEMPTS:
            return False, None, 0

        base_delay = BACKOFF_DELAYS[current_retry_count]
        # Apply ~10-20% jitter
        jitter = random.uniform(0.9, 1.2)
        actual_delay = max(1, int(base_delay * jitter)) if base_delay > 0 else 0

        next_retry_at = datetime.utcnow() + timedelta(seconds=actual_delay)
        return True, next_retry_at, actual_delay


retry_service = RetryService()
