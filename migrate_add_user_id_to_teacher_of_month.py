"""
Migration script to add user_id column to teacher_of_the_month table
Run this once: python migrate_add_user_id_to_teacher_of_month.py
"""
from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        with db.engine.connect() as conn:
            # Check if column exists
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='teacher_of_the_month' AND column_name='user_id'
            """))
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                print("Adding user_id column to teacher_of_the_month table...")
                # Add the column
                conn.execute(text("ALTER TABLE teacher_of_the_month ADD COLUMN user_id INTEGER"))
                conn.commit()
                
                # Check if foreign key constraint already exists
                try:
                    fk_result = conn.execute(text("""
                        SELECT constraint_name
                        FROM information_schema.table_constraints
                        WHERE table_name='teacher_of_the_month' 
                        AND constraint_name='fk_teacher_of_month_user'
                    """))
                    fk_exists = fk_result.fetchone() is not None
                    
                    if not fk_exists:
                        # Add foreign key constraint
                        conn.execute(text("""
                            ALTER TABLE teacher_of_the_month 
                            ADD CONSTRAINT fk_teacher_of_month_user 
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        """))
                        conn.commit()
                        print("✓ Foreign key constraint added")
                except Exception as fk_error:
                    print(f"⚠ Could not add foreign key constraint (may already exist): {fk_error}")
                
                print("✓ Migration complete: user_id column added to teacher_of_the_month")
            else:
                print("✓ user_id column already exists in teacher_of_the_month")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

