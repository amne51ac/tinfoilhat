"""
Tests for the Tinfoil Hat Competition application.

These tests verify the basic functionality of the Flask application.
"""

import os
import tempfile

import pytest

from tinfoilhat.app import create_app
from tinfoilhat.db import get_db, init_db


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


def test_index(client):
    """Test that the index page loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Tinfoil Hat Competition" in response.data


def test_contestant_registration(client):
    """Test adding a new contestant."""
    response = client.post("/contestants", data={"name": "Test Team", "contact_info": "test@example.com"})
    assert response.status_code == 302  # Redirect after successful submission

    # Check that the contestant was added to the database
    with client.application.app_context():
        db = get_db()
        count = db.execute("SELECT COUNT(id) FROM contestant").fetchone()[0]
        assert count == 1
