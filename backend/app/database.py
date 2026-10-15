from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        echo=False,
        connect_args={"check_same_thread": False}
    )
elif settings.database_url.startswith("mysql+pymysql://"):
    engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)
else:
    raise RuntimeError("DATABASE_URL must use mysql+pymysql:// or sqlite:///")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
