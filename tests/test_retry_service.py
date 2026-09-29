import httpx
from app.services.retry_service import RetryService


def test_retry_service_error_classification():
    # Transient HTTP errors
    req = httpx.Request("POST", "https://graph.facebook.com")
    resp_429 = httpx.Response(status_code=429, request=req)
    err_429 = httpx.HTTPStatusError("Rate limit", request=req, response=resp_429)
    assert RetryService.is_transient_error(err_429) is True

    resp_503 = httpx.Response(status_code=503, request=req)
    err_503 = httpx.HTTPStatusError("Service Unavailable", request=req, response=resp_503)
    assert RetryService.is_transient_error(err_503) is True

    timeout_err = httpx.ConnectTimeout("Connection timed out", request=req)
    assert RetryService.is_transient_error(timeout_err) is True

    # Permanent HTTP errors (e.g. invalid payload)
    resp_400 = httpx.Response(status_code=400, request=req)
    err_400 = httpx.HTTPStatusError("Bad Request", request=req, response=resp_400)
    assert RetryService.is_transient_error(err_400) is False

    resp_404 = httpx.Response(status_code=404, request=req)
    err_404 = httpx.HTTPStatusError("Not Found", request=req, response=resp_404)
    assert RetryService.is_transient_error(err_404) is False


def test_retry_backoff_delays():
    # Attempt 1 (index 0)
    can_retry, next_at, delay = RetryService.calculate_next_retry(0)
    assert can_retry is True
    assert delay == 0  # immediate

    # Attempt 2 (index 1)
    can_retry, next_at, delay = RetryService.calculate_next_retry(1)
    assert can_retry is True
    assert 4 <= delay <= 7  # ~5 seconds with jitter

    # Attempt 3 (index 2)
    can_retry, next_at, delay = RetryService.calculate_next_retry(2)
    assert can_retry is True
    assert 25 <= delay <= 38  # ~30 seconds with jitter

    # Attempt 4 (index 3)
    can_retry, next_at, delay = RetryService.calculate_next_retry(3)
    assert can_retry is True
    assert 100 <= delay <= 150  # ~2 minutes with jitter

    # Attempt 5 (index 4)
    can_retry, next_at, delay = RetryService.calculate_next_retry(4)
    assert can_retry is True
    assert 500 <= delay <= 750  # ~10 minutes with jitter

    # Retries exhausted
    can_retry, next_at, delay = RetryService.calculate_next_retry(5)
    assert can_retry is False
    assert next_at is None
