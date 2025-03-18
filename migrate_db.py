"""
Database migration script for the Tinfoil Hat Competition.

This script updates the database schema to include new fields
for phone_number, email, and notes in the contestant table.
"""

import sqlite3
import os
from pathlib import Path

def main():
    """Run the database migration."""
    db_path = Path('instance/tinfoilhat.sqlite')
    
    if not db_path.exists():
        print(f"Database not found at {db_path}. Nothing to migrate.")
        return
    
    print(f"Migrating database at {db_path}...")
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Begin transaction
        conn.execute("BEGIN TRANSACTION")
        
        # Check if the contact_info column exists
        cursor.execute("PRAGMA table_info(contestant)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if "contact_info" in column_names:
            # Step 1: Create temporary table with new schema
            cursor.execute("""
                CREATE TABLE contestant_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone_number TEXT,
                    email TEXT,
                    notes TEXT,
                    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Step 2: Copy data from old table to new table
            cursor.execute("""
                INSERT INTO contestant_new (id, name, notes, created)
                SELECT id, name, contact_info, created FROM contestant
            """)
            
            # Step 3: Drop old table
            cursor.execute("DROP TABLE contestant")
            
            # Step 4: Rename new table to original name
            cursor.execute("ALTER TABLE contestant_new RENAME TO contestant")
            
            # Commit the transaction
            conn.commit()
            print("Migration completed successfully.")
        else:
            print("Migration already applied. No changes needed.")
            conn.rollback()
            
    except Exception as e:
        # Rollback in case of error
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main() 