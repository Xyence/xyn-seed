"""Database configuration and session management."""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://xyn:xyn_dev_password@localhost:5432/xyn")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables.

    In production, use migrations instead of create_all().
    Set XYN_AUTO_CREATE_SCHEMA=true to enable automatic schema creation (dev only).
    Set XYN_REQUIRED_MIGRATIONS to enforce specific migrations (comma-separated).
    """
    auto_create = os.getenv("XYN_AUTO_CREATE_SCHEMA", "false").lower() in ("true", "1", "yes")
    required = os.getenv("XYN_REQUIRED_MIGRATIONS", "001_initial_schema").split(",")

    if auto_create:
        from core import models  # noqa
        Base.metadata.create_all(bind=engine)
        return

    # Production mode: tables must exist via migrations
    from sqlalchemy import inspect, text
    inspector = inspect(engine)

    if "schema_migrations" not in inspector.get_table_names():
        raise RuntimeError(
            "Database schema not initialized. "
            "Run migrations with scripts/apply_migrations.sh or set XYN_AUTO_CREATE_SCHEMA=true for dev."
        )

    # Require baseline (and optionally more)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM schema_migrations")).fetchall()
        applied = {r[0] for r in rows}

    missing = [m.strip() for m in required if m.strip() and m.strip() not in applied]
    if missing:
        raise RuntimeError(
            "Database migrations missing: "
            + ", ".join(missing)
            + ". Run scripts/apply_migrations.sh."
        )
