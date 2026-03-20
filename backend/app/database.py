from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import resolved_database_url


class Base(DeclarativeBase):
    pass


DATABASE_URL = resolved_database_url()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
_session_factory_override = None


def get_session_factory():
    return _session_factory_override or SessionLocal


def set_session_factory_override(factory) -> None:
    global _session_factory_override
    _session_factory_override = factory


def get_db() -> Generator:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
