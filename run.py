"""
Runner script for the Tinfoil Hat Competition application.

This script creates and runs the Flask application.
"""

from tinfoilhat.app import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=True) 