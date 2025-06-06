"""
Flask application factory and configuration.

This module provides the create_app factory function that initializes and configures
the Flask application.
"""

import os
from contextlib import suppress

from flask import Flask

from tinfoilhat import routes
from tinfoilhat.db import close_db, ensure_measurement_cache_exists, init_db


def create_app(test_config=None):
    """
    Create and configure the Flask application.

    :param test_config: Test configuration dictionary to override default config
    :type test_config: dict, optional
    :return: Configured Flask application
    :rtype: Flask
    """
    # Create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        DATABASE=os.path.join(app.instance_path, "tinfoilhat.sqlite"),
        TESTING=False,
    )

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # Ensure the instance folder exists
    with suppress(OSError):
        os.makedirs(app.instance_path)

    # Initialize database only if it doesn't exist
    db_path = app.config["DATABASE"]
    if not os.path.exists(db_path):
        with app.app_context():
            init_db()
            print(f"Created new database at {db_path}")
    else:
        # Make sure measurement_cache table exists
        with app.app_context():
            ensure_measurement_cache_exists()
            print(f"Validated database schema at {db_path}")

    # Register database close function to be called when cleaning up app context
    app.teardown_appcontext(close_db)

    # Register blueprints
    app.register_blueprint(routes.bp)

    return app
