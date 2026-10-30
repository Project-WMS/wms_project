from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_user, require_admin, require_staff
from app.modules.accounts import service
from app.modules.accounts.schemas import ChangePasswordRequest, LoginRequest, RegisterRequest, RoleChangeRequest

router = APIRouter(tags=["Tài khoản & Phân quyền"])


@router.post("/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    return service.register(db, username=req.username, full_name=req.full_name,
                            password=req.password, role=req.role)


@router.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    return service.authenticate(db, req.username, req.password)


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@router.post("/auth/change-password")
def change_password(req: ChangePasswordRequest, user=Depends(current_user), db: Session = Depends(get_db)):
    return service.change_password(db, user["id"], req.old_password, req.new_password)


@router.get("/users")
def list_users(user=Depends(require_staff), db: Session = Depends(get_db)):
    return {"users": service.list_users(db, user)}


@router.post("/users/{user_id}/approve")
def approve_user(user_id: int, actor=Depends(require_staff), db: Session = Depends(get_db)):
    return service.approve(db, actor, user_id)


@router.post("/users/{user_id}/reject")
def reject_user(user_id: int, actor=Depends(require_staff), db: Session = Depends(get_db)):
    return service.reject(db, actor, user_id)


@router.post("/users/{user_id}/lock")
def lock_user(user_id: int, actor=Depends(require_staff), db: Session = Depends(get_db)):
    return service.lock(db, actor, user_id)


@router.post("/users/{user_id}/unlock")
def unlock_user(user_id: int, actor=Depends(require_staff), db: Session = Depends(get_db)):
    return service.unlock(db, actor, user_id)


@router.post("/users/{user_id}/role")
def change_role(user_id: int, req: RoleChangeRequest, actor=Depends(require_admin), db: Session = Depends(get_db)):
    return service.change_role(db, actor, user_id, req.role)
