"""Kết nối PostgreSQL (Supabase) bằng SQLAlchemy + dependency get_db cho FastAPI."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import database_url

# NullPool + prepare_threshold=None để tương thích Supabase Pooler (cổng 6543, transaction mode)
engine = create_engine(
    database_url(),
    echo=False,
    poolclass=NullPool,
    connect_args={"prepare_threshold": None, "connect_timeout": 10},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        # SET LOCAL chỉ có hiệu lực trong transaction hiện tại -> an toàn với connection pooler.
        # Đảm bảo CURRENT_TIMESTAMP luôn là UTC bất kể cấu hình máy chủ DB.
        if engine.dialect.name == "postgresql":
            db.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        yield db
    finally:
        db.close()
