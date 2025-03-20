"""
Tests for the database module of the Tinfoil Hat Competition application.

These tests verify the functionality of the database operations.
"""

import os
import sqlite3
import tempfile

import pytest

from tinfoilhat.app import create_app
from tinfoilhat.db import close_db, get_db, init_db


@pytest.fixture
def app():
    """Create and configure a Flask app for testing."""
    # Create a temporary file to isolate the database for each test
    db_fd, db_path = tempfile.mkstemp()

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": db_path,
        }
    )

    # Create the database and load test data
    with app.app_context():
        init_db()

    yield app

    # Close and remove the temporary database
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


def test_get_db_same_connection(app):
    """Test that get_db returns the same connection within an app context."""
    with app.app_context():
        db = get_db()
        assert db is get_db()  # Test that connections are the same


def test_get_db_close_outside_context(app):
    """Test that the database connection is closed after the app context ends."""
    with app.app_context():
        db = get_db()
        # Store connection for testing after context exit
        conn = db

    # Connection should be accessible but attempting to use it should fail
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_init_db_command(app):
    """Test the init-db command creates the database tables."""
    with app.app_context():
        db = get_db()

        # Query the sqlite_master table to check if our tables exist
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()

        # Convert to a list of table names
        table_names = [table["name"] for table in tables]

        # Check that our expected tables exist
        assert "contestant" in table_names
        assert "test_result" in table_names
        assert "test_data" in table_names
        assert "measurement_cache" in table_names


def test_db_error_handling(app):
    """Test error handling during database operations."""
    # Test with a malformed query
    with app.app_context():
        db = get_db()

        # This should raise an SQLite error
        with pytest.raises(sqlite3.Error):
            db.execute("SELECT * FROM nonexistent_table")


def test_close_db(app):
    """Test the close_db function."""
    with app.app_context():
        db = get_db()
        # Store connection for testing after close
        conn = db

        # Call close_db and check that attempting to use the connection fails
        close_db(None)

        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_db_transaction_commit(app):
    """Test that database transactions are committed correctly."""
    with app.app_context():
        db = get_db()

        # Insert a test contestant
        db.execute("INSERT INTO contestant (name) VALUES (?)", ("Test Team",))
        db.commit()

        # Verify the contestant was added
        contestant = db.execute("SELECT * FROM contestant WHERE name = ?", ("Test Team",)).fetchone()
        assert contestant is not None
        assert contestant["name"] == "Test Team"


def test_db_transaction_rollback(app):
    """Test that database transactions can be rolled back."""
    with app.app_context():
        db = get_db()

        # Start a transaction
        db.execute("INSERT INTO contestant (name) VALUES (?)", ("Rollback Team",))

        # Roll back without committing
        db.rollback()

        # Verify the contestant was not added
        contestant = db.execute("SELECT * FROM contestant WHERE name = ?", ("Rollback Team",)).fetchone()
        assert contestant is None
