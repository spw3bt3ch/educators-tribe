"""
Migration script to add weeks, start_date, and end_date columns to adverts table
Run this script once to update the database schema
"""
from app import app, db
from sqlalchemy import text

def migrate_advert_columns():
    """Add weeks, start_date, and end_date columns to adverts table"""
    with app.app_context():
        try:
            # Check if columns already exist
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'adverts' AND column_name IN ('weeks', 'start_date', 'end_date')
            """))
            existing_columns = [row[0] for row in result]
            
            # Add weeks column if it doesn't exist
            if 'weeks' not in existing_columns:
                print("Adding 'weeks' column to adverts table...")
                db.session.execute(text("""
                    ALTER TABLE adverts 
                    ADD COLUMN weeks INTEGER NOT NULL DEFAULT 1
                """))
                print("✓ Added 'weeks' column")
            
            # Add start_date column if it doesn't exist
            if 'start_date' not in existing_columns:
                print("Adding 'start_date' column to adverts table...")
                db.session.execute(text("""
                    ALTER TABLE adverts 
                    ADD COLUMN start_date TIMESTAMP
                """))
                print("✓ Added 'start_date' column")
            
            # Add end_date column if it doesn't exist
            if 'end_date' not in existing_columns:
                print("Adding 'end_date' column to adverts table...")
                db.session.execute(text("""
                    ALTER TABLE adverts 
                    ADD COLUMN end_date TIMESTAMP
                """))
                print("✓ Added 'end_date' column")
            
            db.session.commit()
            print("\n✅ Migration completed successfully!")
            
            # Verify columns were added
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'adverts' AND column_name IN ('weeks', 'start_date', 'end_date')
            """))
            new_columns = [row[0] for row in result]
            print(f"Verified columns exist: {new_columns}")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error during migration: {e}")
            raise

if __name__ == '__main__':
    print("Starting migration to add weeks, start_date, and end_date columns...\n")
    migrate_advert_columns()

