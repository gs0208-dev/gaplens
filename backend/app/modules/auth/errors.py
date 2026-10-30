from app.core.errors import DomainError
from app.modules.auth.cookies import expired_refresh_cookie_header


class EmailAlreadyRegistered(DomainError):
    status_code = 409
    code = "email_already_registered"
    title = "Email already registered"
    detail = "An account with this email already exists."


class InvalidCredentials(DomainError):
    # One error for a wrong password, an unknown email and a disabled account, so the response
    # never tells an attacker which of the three it was.
    status_code = 401
    code = "invalid_credentials"
    title = "Invalid credentials"
    detail = "The email or password is incorrect."


class InvalidRefreshToken(DomainError):
    # One error for a missing, unknown, expired and reused token, so the response never says
    # which it was. The cookie is cleared so the browser stops sending a dead token.
    status_code = 401
    code = "invalid_refresh_token"
    title = "Session no longer valid"
    detail = "Your session is no longer valid. Sign in again."

    def response_headers(self) -> dict[str, str]:
        return {"Set-Cookie": expired_refresh_cookie_header()}
