"""
Database initialization script for the Tinfoil Hat Competition.

This script creates and initializes the SQLite database with the schema.
"""

from tinfoilhat.app import create_app
from tinfoilhat.db import init_db

# Create a Flask app context and initialize the database
app = create_app()
with app.app_context():
    init_db()
    print("Database initialized successfully.") 