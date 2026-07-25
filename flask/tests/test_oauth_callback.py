import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask, session

from app.views.account_sys import account_sys


class OAuthCallbackTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SECRET_KEY="test-secret-key",
            AUTH_SESSION_ABSOLUTE_LIFETIME=timedelta(hours=12),
        )
        self.app.register_blueprint(account_sys)
        self.client = self.app.test_client()

    def set_oauth_state(self, state="expected-state"):
        with self.client.session_transaction() as client_session:
            client_session["oauth_state"] = state

    @patch("app.views.account_sys.remember_user", return_value=(None, False))
    @patch("app.views.account_sys.APIClient")
    def test_callback_exchanges_token_once_and_stores_application_identity(
        self,
        api_client_class,
        remember_user,
    ):
        oauth_client = Mock()
        oauth_client.oauth.get_access_token.return_value = SimpleNamespace(
            access_token="discord-access-token"
        )
        bearer_client = Mock()
        bearer_client.users.get_current_user.return_value = SimpleNamespace(
            id=123456789,
            username="alice",
            avatar_url="https://cdn.example/avatar.png",
        )
        api_client_class.side_effect = [oauth_client, bearer_client]
        self.set_oauth_state()

        response = self.client.get(
            "/oauth/callback?code=oauth-code&state=expected-state"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
        remember_user.assert_called_once_with("alice")
        bearer_client.users.get_current_user.assert_called_once_with()
        with self.client.session_transaction() as client_session:
            identity = client_session["auth_identity"]
            self.assertEqual(identity["discord_id"], "123456789")
            self.assertEqual(identity["username"], "alice")
            self.assertNotIn("token", client_session)
            self.assertNotIn("discord-access-token", repr(dict(client_session)))

    @patch("app.views.account_sys.remember_user")
    @patch("app.views.account_sys.APIClient")
    def test_callback_rejects_invalid_state_before_discord_request(
        self,
        api_client_class,
        remember_user,
    ):
        self.set_oauth_state()

        response = self.client.get(
            "/oauth/callback?code=oauth-code&state=wrong-state"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        api_client_class.assert_not_called()
        remember_user.assert_not_called()
        with self.client.session_transaction() as client_session:
            self.assertNotIn("auth_identity", client_session)


if __name__ == "__main__":
    unittest.main()
