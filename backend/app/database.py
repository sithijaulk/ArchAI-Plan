from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

if not (settings.database_url.startswith("postgresql://") or settings.database_url.startswith("postgresql+")):
    raise RuntimeError("DATABASE_URL must use PostgreSQL (e.g. postgresql+psycopg2://...)")

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
