"""
Database migration script for Tinfoil Hat Competition.

This script adds the hat_type column to the test_result table if it doesn't exist.
"""

import sys
from pathlib import Path

# Add parent directory to path to import tinfoilhat modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from tinfoilhat.app import create_app
from tinfoilhat.db import get_db, ensure_hat_type_column_exists


def migrate_database():
    """Run database migrations."""
    app = create_app()
    
    with app.app_context():
        db = get_db()
        
        print("Checking for required migrations...")
        
        # Add hat_type column to test_result table
        ensure_hat_type_column_exists()
        
        print("Database migration completed successfully!")


if __name__ == "__main__":
    migrate_database() 