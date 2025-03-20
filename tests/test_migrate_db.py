"""
Tests for the migrate_db module of the Tinfoil Hat Competition application.

These tests verify the database migration functionality.
"""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from tinfoilhat.app import create_app
from tinfoilhat.db import ensure_hat_type_column_exists, get_db, init_db


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

    # Initialize the database with the base schema
    with app.app_context():
        init_db()

    yield app

    # Close and remove the temporary database
    os.close(db_fd)
    os.unlink(db_path)


def test_ensure_hat_type_column_exists(app):
    """Test adding hat_type column to test_result table if it doesn't exist."""
    with app.app_context():
        db = get_db()

        # Simulate a database without the hat_type column by creating a new test_result table
        db.executescript(
            """
        DROP TABLE IF EXISTS test_result;
        CREATE TABLE test_result (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contestant_id INTEGER NOT NULL,
            average_attenuation REAL NOT NULL,
            max_attenuation REAL NOT NULL,
            max_freq REAL NOT NULL,
            min_attenuation REAL NOT NULL,
            min_freq REAL NOT NULL,
            test_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            best_score INTEGER DEFAULT 0
        )
        """
        )
        db.commit()

        # Verify the hat_type column doesn't exist
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT hat_type FROM test_result LIMIT 1")

        # Run the migration function
        with patch("builtins.print"):  # Suppress print statements
            ensure_hat_type_column_exists()

        # Verify that the column now exists
        result = db.execute("PRAGMA table_info(test_result)").fetchall()
        columns = [col["name"] for col in result]
        assert "hat_type" in columns


def test_ensure_measurement_cache_exists(app):
    """Test creating measurement_cache table if it doesn't exist."""
    from tinfoilhat.db import ensure_measurement_cache_exists

    with app.app_context():
        db = get_db()

        # Drop the table if it exists
        db.execute("DROP TABLE IF EXISTS measurement_cache")
        db.commit()

        # Verify the table doesn't exist
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurement_cache'").fetchone()
        assert result is None

        # Run the migration function
        ensure_measurement_cache_exists()

        # Verify the table now exists
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurement_cache'").fetchone()
        assert result is not None

        # Verify the table has the expected structure
        columns = db.execute("PRAGMA table_info(measurement_cache)").fetchall()
        column_names = [col["name"] for col in columns]
        assert "id" in column_names
        assert "type" in column_names
        assert "frequency" in column_names
        assert "power" in column_names
        assert "created" in column_names


def test_migrate_database_function():
    """Test the migrate_database function."""
    from tinfoilhat.migrate_db import migrate_database

    # Mock the app context and ensure_hat_type_column_exists function
    with (
        patch("tinfoilhat.migrate_db.create_app") as mock_create_app,
        patch("tinfoilhat.migrate_db.ensure_hat_type_column_exists") as mock_ensure,
        patch("builtins.print"),
    ):

        # Create a mock app with app_context
        mock_app = mock_create_app.return_value
        mock_app.app_context.return_value.__enter__ = lambda x: None
        mock_app.app_context.return_value.__exit__ = lambda x, y, z, a: None

        # Call the function
        migrate_database()

        # Verify that ensure_hat_type_column_exists was called
        mock_ensure.assert_called_once()
