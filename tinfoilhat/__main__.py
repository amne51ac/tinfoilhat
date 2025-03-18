"""
Main entry point for the Tinfoil Hat Competition application.

This module starts the Flask server and initializes the application.
"""

from tinfoilhat.app import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=True)
