"""
Database initialization script
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from database import init_db, engine
from models import User, UserSchema
from sqlalchemy import text


def create_database():
    """
    Create database if it doesn't exist
    """
    # Connect to MySQL without database
    from sqlalchemy import create_engine
    from config import settings

    # Parse database URL to get connection without database
    db_url_parts = settings.DATABASE_URL.split('/')
    base_url = '/'.join(db_url_parts[:-1])
    db_name = db_url_parts[-1].split('?')[0]

    # Create engine without database
    temp_engine = create_engine(base_url + '/mysql?charset=utf8mb4')

    with temp_engine.connect() as conn:
        # Check if database exists
        result = conn.execute(text(f"SHOW DATABASES LIKE '{db_name}'"))
        if not result.fetchone():
            print(f"Creating database: {db_name}")
            conn.execute(text(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
            conn.commit()
            print(f"Database {db_name} created successfully")
        else:
            print(f"Database {db_name} already exists")

    temp_engine.dispose()


def create_tables():
    """
    Create all tables
    """
    print("Creating tables...")
    init_db()
    print("Tables created successfully")


def verify_tables():
    """
    Verify tables were created
    """
    print("\nVerifying tables...")
    with engine.connect() as conn:
        result = conn.execute(text("SHOW TABLES"))
        tables = [row[0] for row in result]

        print(f"Found {len(tables)} tables:")
        for table in tables:
            print(f"  - {table}")

            # Show table structure
            result = conn.execute(text(f"DESCRIBE {table}"))
            print(f"    Columns:")
            for row in result:
                print(f"      {row[0]} ({row[1]})")


if __name__ == "__main__":
    print("=" * 60)
    print("Finance UI Database Initialization")
    print("=" * 60)

    try:
        # Step 1: Create database
        create_database()

        # Step 2: Create tables
        create_tables()

        # Step 3: Verify
        verify_tables()

        print("\n" + "=" * 60)
        print("Database initialization completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\nError during initialization: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
