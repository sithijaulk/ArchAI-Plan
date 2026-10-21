from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

db_url = settings.database_url or ""

if db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False}
    )
elif db_url.startswith("postgresql://") or db_url.startswith("postgresql+"):
    engine = create_engine(db_url, echo=False, pool_pre_ping=True)
elif db_url.startswith("postgres://"):
    engine = create_engine(db_url, echo=False, pool_pre_ping=True)
else:
    raise RuntimeError("DATABASE_URL must use PostgreSQL (e.g. postgresql+psycopg2://...)")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
