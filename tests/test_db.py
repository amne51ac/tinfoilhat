"""
Tests for the database module of the Tinfoil Hat Competition application.

These tests verify the functionality of the database operations.
"""

import datetime
import os
import sqlite3
import tempfile

import pytest

from tinfoilhat.app import create_app
from tinfoilhat.db import adapt_datetime_iso, close_db, convert_timestamp, get_db, init_db


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


def test_timestamp_adapter():
    """Test the datetime adapter function."""
    now = datetime.datetime(2025, 4, 1, 12, 30, 45)
    result = adapt_datetime_iso(now)
    assert result == "2025-04-01T12:30:45"

    # Test with timezone info
    now_tz = datetime.datetime(2025, 4, 1, 12, 30, 45, tzinfo=datetime.timezone(datetime.timedelta(hours=-5)))
    result_tz = adapt_datetime_iso(now_tz)
    assert result_tz == "2025-04-01T12:30:45-05:00"


def test_timestamp_converter():
    """Test the timestamp converter function."""
    # Test ISO format
    timestamp_str = b"2025-04-01T12:30:45"
    result = convert_timestamp(timestamp_str)
    assert isinstance(result, datetime.datetime)
    assert result.year == 2025
    assert result.month == 4
    assert result.day == 1
    assert result.hour == 12
    assert result.minute == 30
    assert result.second == 45

    # Test standard SQLite format
    sqlite_timestamp = b"2025-04-01 12:30:45"
    result = convert_timestamp(sqlite_timestamp)
    assert isinstance(result, datetime.datetime)
    assert result.year == 2025
    assert result.month == 4
    assert result.day == 1
    assert result.hour == 12
    assert result.minute == 30
    assert result.second == 45


def test_timestamp_storage_and_retrieval(app):
    """Test storing and retrieving timestamps in the database."""
    with app.app_context():
        db = get_db()

        # Create a test table with timestamp column
        db.execute("CREATE TABLE IF NOT EXISTS timestamp_test (id INTEGER PRIMARY KEY, ts TIMESTAMP)")

        # Insert a datetime
        now = datetime.datetime.now()
        db.execute("INSERT INTO timestamp_test (ts) VALUES (?)", (now,))
        db.commit()

        # Retrieve the timestamp
        row = db.execute("SELECT ts FROM timestamp_test").fetchone()
        retrieved_time = row["ts"]

        # Verify it's a datetime object with the same data
        assert isinstance(retrieved_time, datetime.datetime)

        # Compare with original datetime (excluding microseconds which might be truncated)
        assert retrieved_time.year == now.year
        assert retrieved_time.month == now.month
        assert retrieved_time.day == now.day
        assert retrieved_time.hour == now.hour
        assert retrieved_time.minute == now.minute
        assert retrieved_time.second == now.second
