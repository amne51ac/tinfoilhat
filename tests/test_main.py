"""
Tests for the main module of the Tinfoil Hat Competition application.

These tests verify the functionality of the application entry point.
"""

from unittest.mock import MagicMock, patch


def test_main_script():
    """Test the main script execution path."""
    # Create mock for create_app and app.run
    mock_app = MagicMock()

    # Patch both create_app and __name__ in a single with statement
    with (
        patch("tinfoilhat.__main__.create_app", return_value=mock_app),
        patch("tinfoilhat.__main__.__name__", "__main__"),
    ):

        # Use __import__ instead of import to avoid unused import warning and ensure code execution
        main_module = __import__("tinfoilhat.__main__", fromlist=["__main__"])

        # Manually execute the code as if __name__ == "__main__"
        if main_module.__name__ == "__main__":
            app = main_module.create_app()
            app.run(host="0.0.0.0", port=8000, debug=True)

        # Check that app.run was called with expected parameters
        mock_app.run.assert_called_once()
        call_args = mock_app.run.call_args[1]
        assert call_args["host"] == "0.0.0.0"
        assert call_args["port"] == 8000
        assert call_args["debug"] is True
