"""Seed initial packs into the registry"""
import os
import sys
import uuid
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core import models

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://xyn:xyn_dev_password@localhost:5432/xyn")

def seed_packs():
    """Seed initial pack data."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check if core.domain pack already exists
        existing_pack = db.query(models.Pack).filter(
            models.Pack.pack_ref == "core.domain@v1"
        ).first()

        if existing_pack:
            print("Pack core.domain@v1 already exists")
            return

        # Create core.domain pack
        pack = models.Pack(
            id=uuid.uuid4(),
            pack_ref="core.domain@v1",
            name="Core Domain",
            version="1.0.0",
            description="Core domain models for customers and sites",
            schema_name="pack_core_domain",
            manifest={
                "tables": [
                    {
                        "name": "customers",
                        "columns": [
                            {"name": "id", "type": "UUID", "primary_key": True},
                            {"name": "name", "type": "VARCHAR(255)", "nullable": False},
                            {"name": "email", "type": "VARCHAR(255)", "nullable": False, "unique": True},
                            {"name": "status", "type": "VARCHAR(50)", "nullable": False},
                            {"name": "created_at", "type": "TIMESTAMP", "nullable": False},
                            {"name": "updated_at", "type": "TIMESTAMP", "nullable": False}
                        ]
                    },
                    {
                        "name": "sites",
                        "columns": [
                            {"name": "id", "type": "UUID", "primary_key": True},
                            {"name": "customer_id", "type": "UUID", "nullable": False, "foreign_key": "customers.id"},
                            {"name": "name", "type": "VARCHAR(255)", "nullable": False},
                            {"name": "url", "type": "VARCHAR(512)", "nullable": True},
                            {"name": "status", "type": "VARCHAR(50)", "nullable": False},
                            {"name": "created_at", "type": "TIMESTAMP", "nullable": False},
                            {"name": "updated_at", "type": "TIMESTAMP", "nullable": False}
                        ]
                    }
                ],
                "migrations": [],
                "pack_type": "domain",
                "dependencies": []
            },
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(pack)
        db.commit()
        db.refresh(pack)

        print(f"✓ Created pack: {pack.pack_ref} (ID: {pack.id})")
        print(f"  Schema: {pack.schema_name}")
        print(f"  Version: {pack.version}")

    except Exception as e:
        print(f"Error seeding packs: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_packs()
