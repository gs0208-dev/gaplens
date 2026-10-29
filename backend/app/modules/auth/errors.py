from app.core.errors import DomainError


class EmailAlreadyRegistered(DomainError):
    status_code = 409
    code = "email_already_registered"
    title = "Email already registered"
    detail = "An account with this email already exists."
