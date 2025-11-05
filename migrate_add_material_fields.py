"""
Migration script to add Google Drive link and featured image support to educational_materials table
Run this once: python migrate_add_material_fields.py
"""
from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        with db.engine.connect() as conn:
            # Check and add google_drive_link column
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='educational_materials' AND column_name='google_drive_link'
            """))
            if result.fetchone() is None:
                print("Adding google_drive_link column to educational_materials table...")
                conn.execute(text("ALTER TABLE educational_materials ADD COLUMN google_drive_link VARCHAR(1000)"))
                conn.commit()
                print("✓ Added google_drive_link column")
            else:
                print("✓ google_drive_link column already exists")
            
                        # Check and add featured_image_url column
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='educational_materials' AND column_name='featured_image_url'                                                                   
            """))
            if result.fetchone() is None:
                print("Adding featured_image_url column to educational_materials table...")                                                                     
                conn.execute(text("ALTER TABLE educational_materials ADD COLUMN featured_image_url VARCHAR(1000)"))
                conn.commit()
                print("✓ Added featured_image_url column")
            else:
                print("✓ featured_image_url column already exists")

            # Check and add external_url column
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='educational_materials' AND column_name='external_url'                                                                   
            """))
            if result.fetchone() is None:
                print("Adding external_url column to educational_materials table...")                                                                     
                conn.execute(text("ALTER TABLE educational_materials ADD COLUMN external_url VARCHAR(1000)"))
                conn.commit()
                print("✓ Added external_url column")
            else:
                print("✓ external_url column already exists")
            
            # Make file_url nullable (if it's not already)
            result = conn.execute(text("""
                SELECT is_nullable 
                FROM information_schema.columns 
                WHERE table_name='educational_materials' AND column_name='file_url'
            """))
            row = result.fetchone()
            if row and row[0] == 'NO':
                print("Making file_url column nullable...")
                conn.execute(text("ALTER TABLE educational_materials ALTER COLUMN file_url DROP NOT NULL"))
                conn.commit()
                print("✓ Made file_url nullable")
            else:
                print("✓ file_url column is already nullable")
            
            # Make file_name nullable (if it's not already)
            result = conn.execute(text("""
                SELECT is_nullable 
                FROM information_schema.columns 
                WHERE table_name='educational_materials' AND column_name='file_name'
            """))
            row = result.fetchone()
            if row and row[0] == 'NO':
                print("Making file_name column nullable...")
                conn.execute(text("ALTER TABLE educational_materials ALTER COLUMN file_name DROP NOT NULL"))
                conn.commit()
                print("✓ Made file_name nullable")
            else:
                print("✓ file_name column is already nullable")
            
            # Make file_type nullable (if it's not already)
            result = conn.execute(text("""
                SELECT is_nullable 
                FROM information_schema.columns 
                WHERE table_name='educational_materials' AND column_name='file_type'
            """))
            row = result.fetchone()
            if row and row[0] == 'NO':
                print("Making file_type column nullable...")
                conn.execute(text("ALTER TABLE educational_materials ALTER COLUMN file_type DROP NOT NULL"))
                conn.commit()
                print("✓ Made file_type nullable")
            else:
                print("✓ file_type column is already nullable")
            
            print("\n✓ Migration complete! All columns are ready.")
            
    except Exception as e:
        print(f"✗ Error during migration: {e}")
        import traceback
        traceback.print_exc()
