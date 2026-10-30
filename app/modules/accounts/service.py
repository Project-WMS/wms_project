"""FR0 - Đăng ký, đăng nhập, phê duyệt tài khoản theo cấp bậc (BR07)."""
import re

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import create_token, hash_password, is_hashed, verify_password
from app.core.utils import first, placeholders, rows

USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,50}$")
# Cấp cao quản lý cấp thấp: Admin -> manager + worker; Manager -> worker
MANAGEABLE_ROLES = {"admin": ("manager", "worker"), "manager": ("worker",)}
_DUMMY_HASH = hash_password("dummy-password")  # chống dò tài khoản qua thời gian phản hồi


def register(db: Session, *, username: str, full_name: str, password: str, role: str) -> dict:
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "Tên đăng nhập chỉ gồm chữ thường không dấu, số, dấu chấm và gạch dưới (3-50 ký tự)!")
    if role not in ("manager", "worker"):
        raise HTTPException(400, "Chỉ được đăng ký vai trò Thủ kho (manager) hoặc Công nhân (worker)!")
    if db.execute(text("SELECT 1 FROM users WHERE username = :u"), {"u": username}).first():
        raise HTTPException(400, "Tên đăng nhập đã tồn tại!")
    db.execute(text("""
        INSERT INTO users (username, password_hash, full_name, role, approval_status, is_active)
        VALUES (:u, :p, :n, :r, 'pending', FALSE)
    """), {"u": username, "p": hash_password(password), "n": full_name.strip(), "r": role})
    db.commit()
    waiting = "Admin" if role == "manager" else "Thủ kho hoặc Admin"
    return {"message": f"Đăng ký thành công! Tài khoản đang chờ {waiting} phê duyệt."}


def authenticate(db: Session, username: str, password: str) -> dict:
    user = first(db.execute(text("""
        SELECT id, username, password_hash, full_name, role, approval_status, is_active
        FROM users WHERE username = :u
    """), {"u": username.strip().lower()}))
    if not user:
        verify_password(password, _DUMMY_HASH)
        raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu!")
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu!")
    if user["approval_status"] == "pending":
        raise HTTPException(403, "Tài khoản đang chờ Quản lý phê duyệt!")
    if user["approval_status"] == "rejected":
        raise HTTPException(403, "Yêu cầu tạo tài khoản đã bị từ chối!")
    if not user["is_active"]:
        raise HTTPException(403, "Tài khoản đã bị khóa, hãy liên hệ Quản lý!")

    if not is_hashed(user["password_hash"]):  # nâng cấp mật khẩu thô cũ lên dạng băm
        db.execute(text("UPDATE users SET password_hash = :h WHERE id = :id"),
                   {"h": hash_password(password), "id": user["id"]})
        db.commit()

    return {
        "token": create_token(user["id"]),
        "user": {"id": user["id"], "username": user["username"],
                 "full_name": user["full_name"], "role": user["role"]},
    }


def change_password(db: Session, user_id: int, old_password: str, new_password: str) -> dict:
    row = first(db.execute(text("SELECT password_hash FROM users WHERE id = :id"), {"id": user_id}))
    if not row or not verify_password(old_password, row["password_hash"]):
        raise HTTPException(400, "Mật khẩu hiện tại không đúng!")
    if old_password == new_password:
        raise HTTPException(400, "Mật khẩu mới phải khác mật khẩu hiện tại!")
    db.execute(text("UPDATE users SET password_hash = :h WHERE id = :id"),
               {"h": hash_password(new_password), "id": user_id})
    db.commit()
    return {"message": "Đã đổi mật khẩu thành công!"}


def list_users(db: Session, actor: dict) -> list:
    """Danh sách tài khoản cấp dưới mà người dùng hiện tại được quản lý (chờ duyệt xếp trước)."""
    clause, params = placeholders("r", list(MANAGEABLE_ROLES.get(actor["role"], ())))
    return rows(db.execute(text(f"""
        SELECT u.id, u.username, u.full_name, u.role, u.approval_status, u.is_active,
               u.created_at, u.approved_at, a.full_name AS approved_by_name
        FROM users u LEFT JOIN users a ON u.approved_by = a.id
        WHERE u.role IN ({clause})
        ORDER BY CASE WHEN u.approval_status = 'pending' THEN 0 ELSE 1 END, u.created_at DESC, u.id DESC
    """), params))


def _target(db: Session, actor: dict, target_id: int) -> dict:
    target = first(db.execute(text("""
        SELECT id, username, role, approval_status, is_active FROM users WHERE id = :id FOR UPDATE
    """), {"id": target_id}))
    if not target:
        raise HTTPException(404, "Tài khoản không tồn tại!")
    if target["id"] == actor["id"]:
        raise HTTPException(400, "Không thể tự thao tác lên tài khoản của chính mình!")
    if target["role"] not in MANAGEABLE_ROLES.get(actor["role"], ()):
        raise HTTPException(403, "Bạn không có quyền với tài khoản cấp này (BR07)!")
    return target


def approve(db: Session, actor: dict, user_id: int) -> dict:
    t = _target(db, actor, user_id)
    db.execute(text("""
        UPDATE users SET approval_status = 'approved', is_active = TRUE,
                         approved_by = :a, approved_at = CURRENT_TIMESTAMP WHERE id = :id
    """), {"a": actor["id"], "id": user_id})
    db.commit()
    return {"message": f"Đã phê duyệt tài khoản {t['username']}."}


def reject(db: Session, actor: dict, user_id: int) -> dict:
    t = _target(db, actor, user_id)
    db.execute(text("""
        UPDATE users SET approval_status = 'rejected', is_active = FALSE,
                         approved_by = :a, approved_at = CURRENT_TIMESTAMP WHERE id = :id
    """), {"a": actor["id"], "id": user_id})
    db.commit()
    return {"message": f"Đã từ chối tài khoản {t['username']}."}


def lock(db: Session, actor: dict, user_id: int) -> dict:
    t = _target(db, actor, user_id)
    if t["approval_status"] != "approved":
        raise HTTPException(400, "Chỉ khóa được tài khoản đã được duyệt!")
    db.execute(text("UPDATE users SET is_active = FALSE WHERE id = :id"), {"id": user_id})
    db.commit()
    return {"message": f"Đã khóa tài khoản {t['username']}."}


def unlock(db: Session, actor: dict, user_id: int) -> dict:
    t = _target(db, actor, user_id)
    if t["approval_status"] != "approved":
        raise HTTPException(400, "Tài khoản chưa được duyệt, hãy dùng nút Phê duyệt!")
    db.execute(text("UPDATE users SET is_active = TRUE WHERE id = :id"), {"id": user_id})
    db.commit()
    return {"message": f"Đã mở khóa tài khoản {t['username']}."}


def change_role(db: Session, actor: dict, user_id: int, role: str) -> dict:
    """Chỉ Admin được nâng/hạ cấp giữa manager và worker."""
    if actor["role"] != "admin":
        raise HTTPException(403, "Chỉ Admin được thay đổi vai trò nhân sự!")
    if role not in ("manager", "worker"):
        raise HTTPException(400, "Vai trò chỉ có thể là manager hoặc worker!")
    t = _target(db, actor, user_id)
    db.execute(text("UPDATE users SET role = :r WHERE id = :id"), {"r": role, "id": user_id})
    db.commit()
    return {"message": f"Đã đổi vai trò của {t['username']} thành {role}."}
