import math
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.errors import RateLimited, problem_response

LOGIN_LIMIT = "5/minute"
REGISTER_LIMIT = "5/hour"
EMAIL_FAILURE_LIMIT = parse("5/15minutes")

# Per IP address. Counters live in memory, which is enough while there is one backend
# instance (docs/security.md). A moving window avoids the burst a fixed window allows at its edge.
limiter = Limiter(key_func=get_remote_address, strategy="moving-window")


class EmailFailureLimiter:
    """Blocks an email address after too many failed logins, whatever IP they come from.

    The IP limit alone cannot stop one account being attacked from many addresses. Only
    failures are counted, so a person who logs in correctly is never locked out by their own
    logins. The email is counted as submitted, whether or not an account exists, so being
    blocked tells an attacker nothing about which emails are registered.
    """

    def __init__(self) -> None:
        self._storage = MemoryStorage()
        self._strategy = MovingWindowRateLimiter(self._storage)

    def is_blocked(self, email: str) -> bool:
        # test() only looks. It does not use up an attempt.
        return not self._strategy.test(EMAIL_FAILURE_LIMIT, email)

    def record_failure(self, email: str) -> None:
        self._strategy.hit(EMAIL_FAILURE_LIMIT, email)

    def retry_after(self, email: str) -> int:
        stats = self._strategy.get_window_stats(EMAIL_FAILURE_LIMIT, email)
        return max(1, math.ceil(stats.reset_time - time.time()))

    def reset(self) -> None:
        self._storage.reset()


email_failures = EmailFailureLimiter()


def register_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def handle_rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        # slowapi only tells us the window length, so Retry-After is an upper bound.
        window_seconds = exc.limit.limit.get_expiry() if exc.limit is not None else 60
        error = RateLimited(retry_after=window_seconds)
        return problem_response(
            request,
            status_code=error.status_code,
            code=error.code,
            title=error.title,
            detail=error.detail,
            headers=error.response_headers(),
        )
