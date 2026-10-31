import hashlib

# The names are listed in docs/security.md. Keep the two in step.
REGISTER = "auth.register"
LOGIN = "auth.login"
LOGIN_FAILED = "auth.login_failed"
LOGOUT = "auth.logout"
REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"


def email_digest(email: str) -> str:
    """A fingerprint of an email address, so repeated attempts on one address can be matched
    without storing the address itself, or a password typed into the email box by mistake."""
    return hashlib.sha256(email.encode()).hexdigest()
