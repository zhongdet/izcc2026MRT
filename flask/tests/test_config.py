import unittest

from app import validate_secret_key


class SecretKeyConfigTests(unittest.TestCase):
    def test_production_rejects_missing_or_short_secret(self):
        for secret_key in (None, "", "short"):
            with self.subTest(secret_key=secret_key):
                with self.assertRaisesRegex(RuntimeError, "at least 32 characters"):
                    validate_secret_key(True, secret_key)

    def test_production_accepts_long_secret(self):
        validate_secret_key(True, "a" * 32)

    def test_development_allows_generated_secret(self):
        validate_secret_key(False, None)


if __name__ == "__main__":
    unittest.main()
