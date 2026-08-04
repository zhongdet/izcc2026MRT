import logging
from urllib.parse import urlencode

from flask import Blueprint, request, redirect
from zenora import APIClient

from ..config import CLIENT_ID, OAUTH_URL, REDIRECT_URI, CLIENT_SECRET, TOKEN
from ..modules.auth import (
    begin_oauth_login,
    consume_oauth_state,
    sign_in,
    sign_out,
)


log = logging.getLogger(__name__)
account_sys = Blueprint("account_sys", __name__)


def remember_user(username: str) -> tuple[object, bool]:
    from ..core import core

    return core.check_player(username)


@account_sys.route("/oauth/callback")
def callback():
    code = request.args.get("code")
    if not code or not consume_oauth_state(request.args.get("state")):
        log.warning("Rejected Discord OAuth callback with invalid state or code")
        sign_out()
        return redirect("/login")

    try:
        oauth_client = APIClient(TOKEN, client_secret=CLIENT_SECRET, validate_token=False)
        access_token = oauth_client.oauth.get_access_token(code, REDIRECT_URI).access_token
        bearer_client = APIClient(access_token, bearer=True)
        current_user = bearer_client.users.get_current_user()
        avatar_url = getattr(current_user, "avatar_url", None)
        sign_in(
            str(current_user.id),
            current_user.username,
            str(avatar_url) if avatar_url is not None else None,
        )
        _, is_admin = remember_user(current_user.username)

        log.info("User %s is logged in", current_user.username)

        if is_admin:
            return redirect("/admin")
    except Exception:
        log.exception("Discord OAuth callback failed")
        sign_out()
        return redirect("/login")

    return redirect("/")


@account_sys.route("/login")
def login():
    if OAUTH_URL is None or CLIENT_ID is None or CLIENT_SECRET is None:
        log.error("Discord OAuth is not configured")
        return redirect("/")

    state = begin_oauth_login()
    query = urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    })
    return redirect(f"{OAUTH_URL}?{query}")


@account_sys.route("/logout")
def logout():
    sign_out()
    return redirect("/")
