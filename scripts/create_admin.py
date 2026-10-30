"""Tạo tài khoản Admin đầu tiên:  python manage.py create-admin"""
import re
from getpass import getpass

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import hash_password


def run() -> None:
    db = SessionLocal()
    try:
        if db.execute(text("SELECT id FROM users WHERE role = 'admin' LIMIT 1")).first():
            print("Hệ thống đã có tài khoản Admin. Không tạo thêm.")
            return
        full_name = input("Họ tên Admin: ").strip()
        username = input("Tên đăng nhập Admin: ").strip().lower()
        if len(full_name) < 2:
            print("Họ tên phải có ít nhất 2 ký tự.")
            return
        if not re.fullmatch(r"[a-z0-9_.]{3,50}", username):
            print("Tên đăng nhập chỉ gồm chữ thường không dấu, số, '.', '_' (3-50 ký tự).")
            return
        if db.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).first():
            print("Tên đăng nhập đã tồn tại.")
            return
        password, confirm = getpass("Mật khẩu: "), getpass("Nhập lại mật khẩu: ")
        if len(password) < 6:
            print("Mật khẩu phải có ít nhất 6 ký tự.")
            return
        if password != confirm:
            print("Hai mật khẩu không khớp.")
            return
        admin_id = db.execute(text("""
            INSERT INTO users (username, password_hash, full_name, role, approval_status, is_active)
            VALUES (:u, :p, :n, 'admin', 'approved', TRUE) RETURNING id
        """), {"u": username, "p": hash_password(password), "n": full_name}).scalar()
        db.execute(text("UPDATE users SET approved_by = :id, approved_at = CURRENT_TIMESTAMP WHERE id = :id"), {"id": admin_id})
        db.commit()
        print(f"Đã tạo Admin '{username}' (approved, đang hoạt động).")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Không tạo được Admin: {exc}")
    finally:
        db.close()
