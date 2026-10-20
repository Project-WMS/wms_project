
from sqlalchemy import text

from backend.database import engine

try:
    with engine.connect() as ket_noi:
        ket_qua = ket_noi.execute(text("SELECT 1"))
        print("Kết quả kiểm tra:", ket_qua.scalar())
        print("Kết nối PostgreSQL thành công!")
except Exception as loi:
    print("Kết nối PostgreSQL thất bại!")
    print("Chi tiết lỗi:", loi)
finally:
    engine.dispose()
