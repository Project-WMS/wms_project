"""FR0 - Đăng ký, đăng nhập, phê duyệt tài khoản theo cấp bậc (BR07) + dependency phân quyền."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.security import create_token, decode_token, hash_password, is_hashed, verify_password

router = APIRouter(prefix="/api")

ROLE_LEVEL = {"admin": 3, "manager": 2, "worker": 1}


# ---------- Dependency ----------
def current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Lấy user từ header 'Authorization: Bearer <token>'. Kiểm tra lại trạng thái trong DB ở mỗi request
    để việc khóa tài khoản có hiệu lực ngay."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bạn chưa đăng nhập!")
    uid = decode_token(authorization[7:].strip())
    if uid is None:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập hết hạn, vui lòng đăng nhập lại!")
    user = db.execute(text("""
        SELECT id, username, full_name, role, approval_status, is_active FROM users WHERE id = :id
    """), {"id": uid}).mappings().first()
    if not user or user["approval_status"] != "approved" or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Tài khoản không còn hoạt động!")
    return dict(user)


def require_roles(*roles: str):
    def checker(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện chức năng này!")
        return user
    return checker


require_staff = require_roles("admin", "manager")           # thao tác văn phòng (Web PC)
require_any = require_roles("admin", "manager", "worker")   # thao tác quét QR trên Mobile


# ---------- Schemas ----------
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=100)
    role: str = "worker"


class LoginRequest(BaseModel):
    username: str
    password: str


class RoleChangeRequest(BaseModel):
    role: str


# ---------- Đăng ký / Đăng nhập ----------
@router.post("/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    username = req.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.]+", username):
        raise HTTPException(status_code=400, detail="Tên đăng nhập chỉ gồm chữ thường không dấu, số, dấu chấm và gạch dưới!")
    if req.role not in ("manager", "worker"):
        raise HTTPException(status_code=400, detail="Chỉ được đăng ký vai trò Thủ kho (manager) hoặc Công nhân (worker)!")
    exists = db.execute(text("SELECT 1 FROM users WHERE username = :u"), {"u": username}).first()
    if exists:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại!")
    db.execute(text("""
        INSERT INTO users (username, password_hash, full_name, role, approval_status, is_active)
        VALUES (:u, :p, :n, :r, 'pending', FALSE)
    """), {"u": username, "p": hash_password(req.password), "n": req.full_name.strip(), "r": req.role})
    db.commit()
    waiting = "Admin" if req.role == "manager" else "Thủ kho hoặc Admin"
    return {"message": f"Đăng ký thành công! Tài khoản đang chờ {waiting} phê duyệt."}


@router.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(text("""
        SELECT id, username, password_hash, full_name, role, approval_status, is_active
        FROM users WHERE username = :u
    """), {"u": req.username.strip().lower()}).mappings().first()
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu!")
    if user["approval_status"] == "pending":
        raise HTTPException(status_code=403, detail="Tài khoản đang chờ Quản lý phê duyệt!")
    if user["approval_status"] == "rejected":
        raise HTTPException(status_code=403, detail="Yêu cầu tạo tài khoản đã bị từ chối!")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa, hãy liên hệ Quản lý!")

    if not is_hashed(user["password_hash"]):  # nâng cấp mật khẩu thô cũ lên hash
        db.execute(text("UPDATE users SET password_hash = :h WHERE id = :id"),
                   {"h": hash_password(req.password), "id": user["id"]})
        db.commit()

    return {
        "token": create_token(user["id"]),
        "user": {"id": user["id"], "username": user["username"],
                 "full_name": user["full_name"], "role": user["role"]},
    }


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user


# ---------- Quản lý nhân sự & phê duyệt phân cấp (BR07) ----------
def _manageable_roles(actor_role: str):
    """Admin quản lý manager + worker; Manager chỉ quản lý worker; Worker không quản lý ai."""
    return {"admin": ("manager", "worker"), "manager": ("worker",)}.get(actor_role, ())


@router.get("/users")
def list_users(user=Depends(require_staff), db: Session = Depends(get_db)):
    roles = _manageable_roles(user["role"])
    rows = db.execute(text("""
        SELECT u.id, u.username, u.full_name, u.role, u.approval_status, u.is_active,
               u.created_at, a.full_name AS approved_by_name
        FROM users u LEFT JOIN users a ON u.approved_by = a.id
        WHERE u.role = ANY(:roles)
        ORDER BY (u.approval_status = 'pending') DESC, u.created_at DESC
    """), {"roles": list(roles)}).mappings().all()
    return {"users": [dict(r) for r in rows]}


def _target_for_action(db: Session, actor, target_id: int):
    target = db.execute(text("SELECT id, username, role, approval_status, is_active FROM users WHERE id = :id FOR UPDATE"),
                        {"id": target_id}).mappings().first()
    if not target:
        raise HTTPException(status_code=404, detail="Tài khoản không tồn tại!")
    if target["id"] == actor["id"]:
        raise HTTPException(status_code=400, detail="Không thể tự thao tác lên tài khoản của chính mình!")
    if target["role"] not in _manageable_roles(actor["role"]):
        raise HTTPException(status_code=403, detail="Bạn không có quyền với tài khoản cấp này (BR07)!")
    return target


@router.post("/users/{user_id}/approve")
def approve_user(user_id: int, actor=Depends(require_staff), db: Session = Depends(get_db)):
    t = _target_for_action(db, actor, user_id)
    db.execute(text("""
        UPDATE users SET approval_status = 'approved', is_active = TRUE,
                         approved_by = :a, approved_at = CURRENT_TIMESTAMP WHERE id = :id
    """), {"a": actor["id"], "id": user_id})
    db.commit()
    return {"message": f"Đã phê duyệt tài khoản {t['username']}."}


@router.post("/users/{user_id}/reject")
def reject_user(user_id: int, actor=Depends(require_staff), db: Session = Depends(get_db)):
    t = _target_for_action(db, actor, user_id)
    db.execute(text("""
        UPDATE users SET approval_status = 'rejected', is_active = FALSE,
                         approved_by = :a, approved_at = CURRENT_TIMESTAMP WHERE id = :id
    """), {"a": actor["id"], "id": user_id})
    db.commit()
    return {"message": f"Đã từ chối tài khoản {t['username']}."}


@router.post("/users/{user_id}/lock")
def lock_user(user_id: int, actor=Depends(require_staff), db: Session = Depends(get_db)):
    t = _target_for_action(db, actor, user_id)
    if t["approval_status"] != "approved":
        raise HTTPException(status_code=400, detail="Chỉ khóa được tài khoản đã được duyệt!")
    db.execute(text("UPDATE users SET is_active = FALSE WHERE id = :id"), {"id": user_id})
    db.commit()
    return {"message": f"Đã khóa tài khoản {t['username']}."}


@router.post("/users/{user_id}/unlock")
def unlock_user(user_id: int, actor=Depends(require_staff), db: Session = Depends(get_db)):
    t = _target_for_action(db, actor, user_id)
    if t["approval_status"] != "approved":
        raise HTTPException(status_code=400, detail="Tài khoản chưa được duyệt, hãy dùng nút Phê duyệt!")
    db.execute(text("UPDATE users SET is_active = TRUE WHERE id = :id"), {"id": user_id})
    db.commit()
    return {"message": f"Đã mở khóa tài khoản {t['username']}."}


@router.post("/users/{user_id}/role")
def change_role(user_id: int, req: RoleChangeRequest, actor=Depends(require_roles("admin")),
                db: Session = Depends(get_db)):
    """Chỉ Admin được nâng/hạ cấp giữa manager và worker."""
    if req.role not in ("manager", "worker"):
        raise HTTPException(status_code=400, detail="Vai trò chỉ có thể là manager hoặc worker!")
    t = _target_for_action(db, actor, user_id)
    db.execute(text("UPDATE users SET role = :r WHERE id = :id"), {"r": req.role, "id": user_id})
    db.commit()
    return {"message": f"Đã đổi vai trò của {t['username']} thành {req.role}."}
