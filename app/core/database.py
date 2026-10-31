"""Kết nối PostgreSQL (Supabase) bằng SQLAlchemy + dependency get_db cho FastAPI."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import database_url

# Giữ kết nối qua QueuePool + pool_pre_ping để không phải bắt tay TCP/SSL lại tới Supabase ở mỗi request.
# prepare_threshold=None tương thích cả kết nối trực tiếp (5432) lẫn Supabase Pooler (6543).
engine = create_engine(
    database_url(),
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "prepare_threshold": None,
        "connect_timeout": 10,
        "options": "-c timezone=UTC",
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
