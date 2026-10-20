import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Nạp biến môi trường từ file .env ở thư mục gốc
load_dotenv()

db_url = os.getenv("DATABASE_URL")

if not db_url:
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "wms_db")
    db_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(db_url, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Hàm cung cấp kết nối CSDL cho các API của FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()