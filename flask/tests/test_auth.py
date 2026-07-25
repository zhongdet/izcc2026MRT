import unittest
from datetime import timedelta

from flask import Flask, jsonify, session
from flask.sessions import SecureCookieSessionInterface

from app.modules.auth import (
    begin_oauth_login,
    consume_oauth_state,
    current_identity,
    sign_in,
    sign_out,
)


class AuthSessionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SECRET_KEY="test-secret-key",
            AUTH_SESSION_ABSOLUTE_LIFETIME=timedelta(hours=12),
        )
        self.context = self.app.test_request_context()
        self.context.push()

    def tearDown(self):
        self.context.pop()

    def test_sign_in_stores_only_application_identity(self):
        sign_in("123456789", "alice", "https://cdn.example/avatar.png", now=1000)

        identity = current_identity(now=1001)

        self.assertEqual(identity.discord_id, "123456789")
        self.assertEqual(identity.username, "alice")
        self.assertEqual(identity.avatar_url, "https://cdn.example/avatar.png")
        self.assertTrue(session.permanent)
        self.assertNotIn("token", session)
        self.assertNotIn("access_token", repr(dict(session)))

    def test_absolute_expiry_clears_the_session(self):
        self.app.config["AUTH_SESSION_ABSOLUTE_LIFETIME"] = timedelta(seconds=10)
        sign_in("123456789", "alice", None, now=1000)

        self.assertIsNone(current_identity(now=1011))
        self.assertNotIn("auth_identity", session)

    def test_sign_out_removes_identity(self):
        sign_in("123456789", "alice", None, now=1000)

        sign_out()

        self.assertIsNone(current_identity(now=1001))

    def test_oauth_state_is_random_and_single_use(self):
        state = begin_oauth_login()

        self.assertGreaterEqual(len(state), 32)
        self.assertTrue(consume_oauth_state(state))
        self.assertFalse(consume_oauth_state(state))

    def test_oauth_state_mismatch_is_rejected_and_consumed(self):
        state = begin_oauth_login()

        self.assertFalse(consume_oauth_state("wrong-state"))
        self.assertFalse(consume_oauth_state(state))


class SignedCookieTests(unittest.TestCase):
    @staticmethod
    def make_app(secret_key):
        app = Flask(__name__)
        app.config.update(
            SECRET_KEY=secret_key,
            AUTH_SESSION_ABSOLUTE_LIFETIME=timedelta(hours=12),
        )

        @app.route("/test-login")
        def test_login():
            sign_in("123456789", "alice", None)
            return "ok"

        @app.route("/whoami")
        def whoami():
            identity = current_identity()
            if identity is None:
                return jsonify({"error": "unauthorized"}), 401
            return jsonify({
                "discord_id": identity.discord_id,
                "username": identity.username,
            })

        return app

    def test_legitimate_signed_cookie_is_accepted(self):
        app = self.make_app("server-secret")
        client = app.test_client()

        client.get("/test-login")
        response = client.get("/whoami")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["discord_id"], "123456789")

    def test_public_identity_cannot_be_forged_with_another_key(self):
        victim_app = self.make_app("server-secret")
        attacker_app = self.make_app("attacker-secret")
        serializer = SecureCookieSessionInterface().get_signing_serializer(attacker_app)
        forged_cookie = serializer.dumps({
            "auth_identity": {
                "discord_id": "123456789",
                "username": "alice",
                "avatar_url": None,
                "authenticated_at": 9999999999,
            },
            "_permanent": True,
        })
        client = victim_app.test_client()
        client.set_cookie(victim_app.config["SESSION_COOKIE_NAME"], forged_cookie)

        response = client.get("/whoami")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
