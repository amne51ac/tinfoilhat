"""
Database module for the Tinfoil Hat Competition application.

This module handles database connections and schema initialization.
"""

import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext


def get_db():
    """
    Get a database connection.

    :return: SQLite database connection
    :rtype: sqlite3.Connection
    """
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row

    return g.db


def close_db(e=None):
    """
    Close the database connection.

    :param e: Error that triggered the close, defaults to None
    :type e: Exception, optional
    """
    db = g.pop("db", None)

    if db is not None:
        db.close()


def ensure_measurement_cache_exists():
    """
    Ensure the measurement_cache table exists in the database.
    """
    db = get_db()

    # Check if measurement_cache table exists
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurement_cache'")
    if cursor.fetchone() is None:
        # Create the measurement_cache table
        db.execute(
            """
        CREATE TABLE IF NOT EXISTS measurement_cache (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          type TEXT NOT NULL,
          frequency INTEGER NOT NULL,
          power REAL NOT NULL,
          created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(type, frequency)
        )
        """
        )
        db.commit()


def ensure_hat_type_column_exists():
    """
    Ensure the hat_type column exists in the test_result table.
    This is a migration for existing databases.
    """
    db = get_db()

    # Check if hat_type column exists in test_result table
    try:
        db.execute("SELECT hat_type FROM test_result LIMIT 1")
    except Exception:
        # Add hat_type column with default value 'classic'
        db.execute("ALTER TABLE test_result ADD COLUMN hat_type TEXT DEFAULT 'classic'")
        db.commit()
        print("Added hat_type column to test_result table")


def init_db():
    """
    Initialize the database with schema.
    """
    db = get_db()

    schema_path = Path(__file__).parent / "schema.sql"
    with schema_path.open("r") as f:
        db.executescript(f.read())

    # Make sure the measurement_cache table exists
    ensure_measurement_cache_exists()

    # Make sure the hat_type column exists in test_result
    ensure_hat_type_column_exists()


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo("Initialized the database.")
