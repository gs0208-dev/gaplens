from fastapi import Response

REFRESH_COOKIE_NAME = "refresh_token"
# The cookie is only sent to the auth endpoints, never with ordinary API requests.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,  # scripts cannot read it, so XSS cannot steal it
        secure=True,  # HTTPS only (browsers also allow it on localhost)
        samesite="strict",  # never sent on cross-site requests
    )


def clear_refresh_cookie(response: Response) -> None:
    # A browser only deletes a cookie when the name, path and attributes match the one it holds.
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )


def expired_refresh_cookie_header() -> str:
    """The Set-Cookie value that makes a browser delete the refresh cookie."""
    response = Response()
    clear_refresh_cookie(response)
    return response.headers["set-cookie"]
