"""
SQLAlchemy 2.0 declarative base, engine, and session factory.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from gitd.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


def _build_engine():
    """Create a SQLite engine with WAL mode and foreign keys enabled."""
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a SQLAlchemy session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added to a table AFTER it first shipped. create_all() only creates
# missing TABLES, never adds columns to an existing one, so existing databases
# need an idempotent ALTER. Fresh DBs already have these from the model defs.
_ADDITIVE_COLUMNS = [
    ("skill_runs", "kind", "TEXT NOT NULL DEFAULT 'hard'"),
    ("skill_compat", "kind", "TEXT NOT NULL DEFAULT 'hard'"),
]


def ensure_additive_columns() -> None:
    """Idempotently add post-hoc columns to existing tables. Call after create_all."""
    from sqlalchemy import text as _sql

    with engine.begin() as conn:
        for table, col, decl in _ADDITIVE_COLUMNS:
            try:
                conn.execute(_sql(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))
            except Exception:
                pass  # column already present or table absent — safe to ignore
