
import re
from getpass import getpass

from sqlalchemy import text

from backend.database import SessionLocal
from backend.security import hash_password


def tao_tai_khoan_admin():
    db = SessionLocal()

    try:
        # Không tạo thêm Admin nếu đã có Admin
        admin_hien_co = db.execute(
            text("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        ).first()

        if admin_hien_co:
            print("Hệ thống đã có tài khoản Admin.")
            print("Không tạo thêm tài khoản mới.")
            return

        # Nhập thông tin tài khoản
        ho_ten = input("Nhập họ tên Admin: ").strip()
        ten_dang_nhap = input(
            "Nhập tên đăng nhập Admin: "
        ).strip().lower()

        if len(ho_ten) < 2:
            print("Họ tên phải có ít nhất 2 ký tự.")
            return

        if not re.fullmatch(r"[a-z0-9_.]{3,50}", ten_dang_nhap):
            print("Tên đăng nhập không hợp lệ.")
            return

        # Kiểm tra username đã tồn tại chưa
        tai_khoan = db.execute(
            text("SELECT id FROM users WHERE username = :u"),
            {"u": ten_dang_nhap},
        ).first()

        if tai_khoan:
            print("Tên đăng nhập đã tồn tại.")
            return

        mat_khau = getpass("Nhập mật khẩu Admin: ")
        xac_nhan = getpass("Nhập lại mật khẩu: ")

        if len(mat_khau) < 6:
            print("Mật khẩu phải có ít nhất 6 ký tự.")
            return

        if mat_khau != xac_nhan:
            print("Hai mật khẩu không khớp.")
            return

        # Lưu Admin với mật khẩu đã được băm
        admin_id = db.execute(
            text("""
                INSERT INTO users (
                    username,
                    password_hash,
                    full_name,
                    role,
                    approval_status,
                    is_active
                )
                VALUES (
                    :username,
                    :password_hash,
                    :full_name,
                    'admin',
                    'approved',
                    TRUE
                )
                RETURNING id
            """),
            {
                "username": ten_dang_nhap,
                "password_hash": hash_password(mat_khau),
                "full_name": ho_ten,
            },
        ).scalar_one()

        # Ghi nhận Admin đầu tiên là người phê duyệt tài khoản của mình
        db.execute(
            text("""
                UPDATE users
                SET approved_by = :id,
                    approved_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"id": admin_id},
        )

        db.commit()

        print("\nTạo tài khoản Admin thành công!")
        print(f"Tên đăng nhập: {ten_dang_nhap}")
        print("Vai trò: admin")
        print("Trạng thái: approved, đang hoạt động")

    except Exception as loi:
        db.rollback()
        print(f"\nKhông tạo được Admin: {loi}")

    finally:
        db.close()


if __name__ == "__main__":
    tao_tai_khoan_admin()
