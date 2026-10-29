from app.core.errors import DomainError


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
