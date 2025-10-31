"""
Quick migration script to add image_url column to blog_posts table
Run this once: python migrate_add_image_url.py
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
                WHERE table_name='blog_posts' AND column_name='image_url'
            """))
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                print("Adding image_url column to blog_posts table...")
                conn.execute(text("ALTER TABLE blog_posts ADD COLUMN image_url VARCHAR(1000)"))
                conn.commit()
                print("✓ Migration complete: image_url column added to blog_posts")
            else:
                print("✓ image_url column already exists in blog_posts")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

