"""Bootstrap the core.domain pack by creating schema and tables"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://xyn:xyn_dev_password@localhost:5432/xyn")

def bootstrap_domain_pack():
    """Create schema and tables for core.domain pack."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Create schema
        print("Creating schema pack_core_domain...")
        db.execute(text("CREATE SCHEMA IF NOT EXISTS pack_core_domain"))
        db.commit()
        print("✓ Schema created")

        # Create customers table
        print("Creating customers table...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS pack_core_domain.customers (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                status VARCHAR(50) NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """))
        db.commit()
        print("✓ Customers table created")

        # Create sites table
        print("Creating sites table...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS pack_core_domain.sites (
                id UUID PRIMARY KEY,
                customer_id UUID NOT NULL REFERENCES pack_core_domain.customers(id),
                name VARCHAR(255) NOT NULL,
                url VARCHAR(512),
                status VARCHAR(50) NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """))
        db.commit()
        print("✓ Sites table created")

        print("\n✓ Pack core.domain@v1 bootstrapped successfully!")
        print("  Schema: pack_core_domain")
        print("  Tables: customers, sites")

    except Exception as e:
        print(f"Error bootstrapping pack: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap_domain_pack()
