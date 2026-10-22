import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)

# Validate PostgreSQL connection string
if not (settings.database_url.startswith("postgresql://") or settings.database_url.startswith("postgresql+")):
    raise RuntimeError("DATABASE_URL must use PostgreSQL (e.g. postgresql+psycopg2://...)")


engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"connect_timeout": 3},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
