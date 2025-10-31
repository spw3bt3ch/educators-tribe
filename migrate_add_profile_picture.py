"""
Quick migration script to add profile_picture column to users table
Run this once: python migrate_add_profile_picture.py
"""
from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        # Check if column exists
        with db.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='profile_picture'
            """))
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                print("Adding profile_picture column to users table...")
                conn.execute(text("ALTER TABLE users ADD COLUMN profile_picture VARCHAR(1000)"))
                conn.commit()
                print("✓ Migration complete: profile_picture column added to users")
            else:
                print("✓ profile_picture column already exists in users")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

