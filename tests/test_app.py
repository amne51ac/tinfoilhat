"""
Tests for the Tinfoil Hat Competition application.

These tests verify the basic functionality of the Flask application.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from tinfoilhat.app import create_app
from tinfoilhat.db import get_db, init_db
from tinfoilhat.routes import save_results


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


def test_server_side_calculation_logic():
    """Test that server-side calculations correctly process only valid measurements."""
    # Create a mock app context and request
    app = create_app({"TESTING": True})

    with app.app_context(), app.test_request_context():
        # Setup test data with frequencies that match RF band definitions
        app.config["BASELINE_DATA"] = {
            "20000000": -80.0,  # 20 MHz (HF: 2-30 MHz)
            "150000000": -81.5,  # 150 MHz (VHF: 30-300 MHz)
            "700000000": -82.5,  # 700 MHz (UHF: 300-3000 MHz)
            "5000000000": -83.0,  # 5 GHz (SHF: 3000-5900 MHz)
        }

        app.config["HAT_DATA"] = {
            "20000000": -82.0,  # 20 MHz (2.0 dB attenuation)
            "150000000": -85.5,  # 150 MHz (4.0 dB attenuation)
            "700000000": -87.5,  # 700 MHz (5.0 dB attenuation)
            "5000000000": -83.5,  # 5 GHz (0.5 dB attenuation)
        }

        # Mock the get_scanner function to return a scanner with correct frequencies that match RF bands
        scanner_mock = MagicMock()
        scanner_mock.frequencies = [20.0, 150.0, 700.0, 5000.0]  # MHz

        # Create a side effect function that returns the expected attenuation values
        def calculate_att(baseline, hat):
            print("DEBUG TEST - Mock calculate_attenuation called with baseline and hat measurements")
            # Return the expected attenuation values
            return [2.0, 4.0, 5.0, 0.5]  # dB

        scanner_mock.calculate_attenuation.side_effect = calculate_att

        # Mock the database to prevent actual DB operations
        db_mock = MagicMock()
        db_mock.execute.return_value = MagicMock()
        db_mock.execute().fetchone.return_value = None

        # Test with patched dependencies
        with patch("tinfoilhat.routes.get_scanner", return_value=scanner_mock), patch(
            "tinfoilhat.routes.get_db", return_value=db_mock
        ), patch("tinfoilhat.routes.request") as request_mock, patch("tinfoilhat.routes.clear_measurements"):

            # Configure the mock request
            request_mock.json = {"contestant_id": "1"}

            # Call the function
            response = save_results()
            result = json.loads(response.data)

            # Debug output to help diagnose
            print(f"DEBUG TEST - Result effectiveness: {result['data']['effectiveness']}")

            # Verify the response contains correctly calculated values
            assert result["status"] == "success"
            assert abs(result["data"]["average_attenuation"] - 2.875) < 0.001  # Average of [2.0, 4.0, 5.0, 0.5]

            # Check band calculations - we're using standard RF bands
            # In our updated test data, we have:
            # - 1 HF (20 MHz): 2.0 dB attenuation
            # - 1 VHF (150 MHz): 4.0 dB attenuation
            # - 1 UHF (700 MHz): 5.0 dB attenuation
            # - 1 SHF (5 GHz): 0.5 dB attenuation
            assert result["data"]["effectiveness"]["hf_band"] == 2.0
            assert result["data"]["effectiveness"]["vhf_band"] == 4.0
            assert result["data"]["effectiveness"]["uhf_band"] == 5.0
            assert result["data"]["effectiveness"]["shf_band"] == 0.5

            # Check max/min identification
            assert result["data"]["max_attenuation"]["value"] == 5.0  # Highest attenuation
            assert result["data"]["min_attenuation"]["value"] == 0.5  # Lowest attenuation
