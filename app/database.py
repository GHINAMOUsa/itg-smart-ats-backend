from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """
    Dependency that yields a database session and ensures it is closed afterwards.
    Use with Depends(get_db) in route handlers.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
