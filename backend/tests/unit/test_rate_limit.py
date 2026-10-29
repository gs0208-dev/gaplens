from app.core.rate_limit import EmailFailureLimiter

EMAIL = "ana@example.com"


def test_email_is_not_blocked_before_five_failures() -> None:
    limiter = EmailFailureLimiter()

    for _ in range(4):
        limiter.record_failure(EMAIL)

    assert not limiter.is_blocked(EMAIL)


def test_email_is_blocked_after_five_failures() -> None:
    limiter = EmailFailureLimiter()

    for _ in range(5):
        limiter.record_failure(EMAIL)

    assert limiter.is_blocked(EMAIL)


def test_checking_does_not_count_as_a_failure() -> None:
    limiter = EmailFailureLimiter()

    for _ in range(20):
        limiter.is_blocked(EMAIL)

    assert not limiter.is_blocked(EMAIL)


def test_emails_are_counted_separately() -> None:
    limiter = EmailFailureLimiter()

    for _ in range(5):
        limiter.record_failure(EMAIL)

    assert not limiter.is_blocked("bob@example.com")


def test_retry_after_is_within_the_fifteen_minute_window() -> None:
    limiter = EmailFailureLimiter()
    for _ in range(5):
        limiter.record_failure(EMAIL)

    assert 0 < limiter.retry_after(EMAIL) <= 15 * 60


def test_reset_clears_every_counter() -> None:
    limiter = EmailFailureLimiter()
    for _ in range(5):
        limiter.record_failure(EMAIL)

    limiter.reset()

    assert not limiter.is_blocked(EMAIL)
