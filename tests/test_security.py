"""Kiểm thử các hàm bảo mật thuần (không cần CSDL):  python -m unittest tests.test_security -v"""
import base64
import json
import unittest

from app.core import security


class SecurityTests(unittest.TestCase):
    def test_password_hash_roundtrip(self):
        h = security.hash_password("abc123")
        self.assertTrue(security.is_hashed(h))
        self.assertTrue(security.verify_password("abc123", h))
        self.assertFalse(security.verify_password("sai-mat-khau", h))

    def test_hash_is_salted(self):
        self.assertNotEqual(security.hash_password("abc123"), security.hash_password("abc123"))

    def test_legacy_plain_password(self):
        self.assertFalse(security.is_hashed("123456"))
        self.assertTrue(security.verify_password("123456", "123456"))
        self.assertFalse(security.verify_password("1234567", "123456"))

    def test_jwt_roundtrip_and_shape(self):
        token = security.create_token(7)
        self.assertEqual(token.count("."), 2)
        header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
        self.assertEqual(header, {"alg": "HS256", "typ": "JWT"})
        self.assertEqual(security.decode_token(token), 7)

    def test_jwt_tamper_rejected(self):
        header, payload, sig = security.create_token(7).split(".")
        forged = base64.urlsafe_b64encode(json.dumps({"sub": "1", "exp": 9999999999}).encode()).decode().rstrip("=")
        self.assertIsNone(security.decode_token(f"{header}.{forged}.{sig}"))
        self.assertIsNone(security.decode_token("khong-phai-token"))
        self.assertIsNone(security.decode_token(""))

    def test_jwt_expired(self):
        original = security.TOKEN_TTL_SECONDS
        security.TOKEN_TTL_SECONDS = -10
        try:
            self.assertIsNone(security.decode_token(security.create_token(7)))
        finally:
            security.TOKEN_TTL_SECONDS = original


if __name__ == "__main__":
    unittest.main()
