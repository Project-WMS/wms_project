"""Băm mật khẩu + token đăng nhập, chỉ dùng thư viện chuẩn của Python (không cần cài thêm gói)."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 12 * 60 * 60  # 1 ca làm việc


def _secret_key() -> bytes:
    key = os.getenv("WMS_SECRET_KEY")
    if key:
        return key.encode()
    # Dự phòng cho môi trường dev: ổn định qua các lần restart nhưng KHÔNG an toàn bằng khóa riêng.
    # Khi triển khai thật hãy đặt WMS_SECRET_KEY trong .env.
    seed = (os.getenv("DB_PASSWORD", "") + os.getenv("DB_NAME", "wms_db") + "wms-dev-secret")
    return hashlib.sha256(seed.encode()).digest()


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
        # Tài khoản cũ còn lưu mật khẩu thô: so sánh an toàn, đăng nhập xong sẽ được nâng cấp lên hash.
        return hmac.compare_digest(password.encode(), stored.encode())
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user_id: int) -> str:
    payload = _b64(json.dumps({"uid": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS}).encode())
    sig = _b64(hmac.new(_secret_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def decode_token(token: str) -> Optional[int]:
    """Trả về user_id nếu token hợp lệ và chưa hết hạn, ngược lại None."""
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(_secret_key(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        if data["exp"] < time.time():
            return None
        return int(data["uid"])
    except Exception:
        return None
