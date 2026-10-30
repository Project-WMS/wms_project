"""Băm mật khẩu PBKDF2-HMAC-SHA256 + JWT HS256 (chỉ dùng thư viện chuẩn của Python)."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from app.core.config import TOKEN_TTL_SECONDS, secret_key

PBKDF2_ITERATIONS = 200_000


# ---------- Mật khẩu ----------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def is_hashed(stored: str) -> bool:
    return bool(stored) and stored.startswith("pbkdf2$")


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if not is_hashed(stored):
        # Tài khoản cũ còn lưu mật khẩu thô: so sánh an toàn, sẽ được nâng cấp lên hash khi đăng nhập
        return hmac.compare_digest(password.encode(), stored.encode())
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


# ---------- JWT (HS256) ----------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(signing_input: str) -> str:
    return _b64(hmac.new(secret_key(), signing_input.encode(), hashlib.sha256).digest())


def create_token(user_id: int) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL_SECONDS},
                              separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}"
    return f"{signing_input}.{_sign(signing_input)}"


def decode_token(token: str) -> Optional[int]:
    """Trả về user_id nếu token hợp lệ và chưa hết hạn, ngược lại None."""
    try:
        header, payload, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(f"{header}.{payload}")):
            return None
        if json.loads(_unb64(header)).get("alg") != "HS256":
            return None
        data = json.loads(_unb64(payload))
        if data["exp"] < time.time():
            return None
        return int(data["sub"])
    except Exception:
        return None
