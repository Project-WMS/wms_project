"""Dependency xác thực & phân quyền dùng chung cho mọi router."""
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token


def current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Lấy user từ header 'Authorization: Bearer <token>'.
    Đọc lại trạng thái trong DB ở mỗi request nên việc khóa tài khoản có hiệu lực ngay."""
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


require_admin = require_roles("admin")
require_staff = require_roles("admin", "manager")           # thao tác văn phòng (Web PC)
require_any = require_roles("admin", "manager", "worker")   # thao tác quét QR trên Mobile
