import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from flask import current_app, session


AUTH_IDENTITY_KEY = "auth_identity"
OAUTH_STATE_KEY = "oauth_state"


@dataclass(frozen=True)
class AuthIdentity:
    discord_id: str
    username: str
    avatar_url: Optional[str] = None


def begin_oauth_login() -> str:
    """Start a fresh OAuth flow and return its one-time state value."""
    session.clear()
    state = secrets.token_urlsafe(32)
    session[OAUTH_STATE_KEY] = state
    return state


def consume_oauth_state(received_state: Optional[str]) -> bool:
    """Validate and consume the OAuth state, whether validation succeeds or not."""
    expected_state = session.pop(OAUTH_STATE_KEY, None)
    if not isinstance(expected_state, str) or not isinstance(received_state, str):
        return False
    return hmac.compare_digest(expected_state, received_state)


def sign_in(
    discord_id: str,
    username: str,
    avatar_url: Optional[str],
    *,
    now: Optional[float] = None,
) -> None:
    """Replace the current session with a Discord-verified application identity."""
    authenticated_at = time.time() if now is None else now
    session.clear()
    session[AUTH_IDENTITY_KEY] = {
        "discord_id": str(discord_id),
        "username": username,
        "avatar_url": avatar_url,
        "authenticated_at": authenticated_at,
    }
    session.permanent = True


def sign_out() -> None:
    session.clear()


def current_identity(*, now: Optional[float] = None) -> Optional[AuthIdentity]:
    """Return the signed-in identity when the session is valid and unexpired."""
    payload = session.get(AUTH_IDENTITY_KEY)
    if not isinstance(payload, dict):
        return None

    discord_id = payload.get("discord_id")
    username = payload.get("username")
    avatar_url = payload.get("avatar_url")
    authenticated_at = payload.get("authenticated_at")

    if (
        not isinstance(discord_id, str)
        or not discord_id
        or not isinstance(username, str)
        or not username
        or (avatar_url is not None and not isinstance(avatar_url, str))
        or not isinstance(authenticated_at, (int, float))
    ):
        sign_out()
        return None

    lifetime = current_app.config["AUTH_SESSION_ABSOLUTE_LIFETIME"]
    if isinstance(lifetime, timedelta):
        lifetime_seconds = lifetime.total_seconds()
    else:
        lifetime_seconds = float(lifetime)

    current_time = time.time() if now is None else now
    if current_time >= authenticated_at + lifetime_seconds:
        sign_out()
        return None

    return AuthIdentity(
        discord_id=discord_id,
        username=username,
        avatar_url=avatar_url,
    )
