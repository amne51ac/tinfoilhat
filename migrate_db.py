#!/usr/bin/env python
"""
Database migration script for the Tinfoil Hat Competition application.

This script updates the database schema without destroying existing data.
"""

import os
import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path):
    """
    Migrate the database to the latest schema version.
    
    :param db_path: Path to the SQLite database file
    :type db_path: str
    :return: True if successful, False otherwise
    :rtype: bool
    """
    print(f"Migrating database at: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return False
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get list of existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row['name'] for row in cursor.fetchall()]
        print(f"Existing tables: {', '.join(tables)}")
        
        # Add measurement_cache table if it doesn't exist
        if 'measurement_cache' not in tables:
            print("Adding measurement_cache table...")
            cursor.execute("""
            CREATE TABLE measurement_cache (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              type TEXT NOT NULL,
              frequency INTEGER NOT NULL,
              power REAL NOT NULL,
              created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(type, frequency)
            )
            """)
            print("measurement_cache table created successfully.")
        else:
            print("measurement_cache table already exists, skipping.")
            
        conn.commit()
        print("Migration completed successfully!")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {str(e)}")
        return False
        
    finally:
        conn.close()

def main():
    """Main function to run the migration."""
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Default path is in the instance folder
        script_dir = Path(__file__).parent
        instance_dir = script_dir / 'instance'
        db_path = instance_dir / 'tinfoilhat.sqlite'
    
    print(f"Using database path: {db_path}")
    
    if not migrate_database(str(db_path)):
        print("Migration failed!")
        return 1
        
    return 0

if __name__ == '__main__':
    sys.exit(main()) 