"""
Routes module for the Tinfoil Hat Competition application.

This module defines all HTTP endpoints for the Flask application.
"""

import json

from flask import (
    Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
)

from tinfoilhat.db import get_db
from tinfoilhat.scanner import Scanner

bp = Blueprint("tinfoilhat", __name__, url_prefix='')

# Create a scanner instance
scanner = Scanner(samples_per_freq=100)  # 100 samples per frequency for more stable readings


@bp.route("/", methods=["GET"])
def index():
    """
    Main application page with leaderboard and test controls.
    
    :return: Rendered template for the main page
    :rtype: str
    """
    # Get leaderboard data - only the best scores per contestant
    db = get_db()
    leaderboard = db.execute(
        """
        SELECT c.name, t.average_attenuation, t.test_date 
        FROM contestant c
        JOIN test_result t ON c.id = t.contestant_id
        WHERE t.is_best_score = 1
        ORDER BY t.average_attenuation DESC
        """
    ).fetchall()
    
    # Get all contestants for the dropdown
    contestants = db.execute("SELECT id, name FROM contestant").fetchall()
    
    return render_template(
        "index.html", 
        leaderboard=leaderboard, 
        contestants=contestants
    )


@bp.route("/leaderboard", methods=["GET"])
def get_leaderboard():
    """
    API endpoint to fetch the current leaderboard data.
    
    :return: JSON response with leaderboard data
    :rtype: Response
    """
    db = get_db()
    leaderboard = db.execute(
        """
        SELECT c.name, t.average_attenuation, t.test_date 
        FROM contestant c
        JOIN test_result t ON c.id = t.contestant_id
        WHERE t.is_best_score = 1
        ORDER BY t.average_attenuation DESC
        """
    ).fetchall()
    
    # Convert to list of dictionaries for JSON serialization
    leaderboard_data = []
    for i, row in enumerate(leaderboard):
        leaderboard_data.append({
            "rank": i + 1,
            "name": row["name"],
            "average_attenuation": row["average_attenuation"],
            "test_date": row["test_date"]
        })
    
    return jsonify({"leaderboard": leaderboard_data})


@bp.route("/contestants", methods=["POST"])
def add_contestant():
    """
    Add a new contestant.
    
    :return: Redirect to the main page
    :rtype: Response
    """
    name = request.form.get("name")
    phone_number = request.form.get("phone_number", "")
    email = request.form.get("email", "")
    notes = request.form.get("notes", "")
    
    if not name:
        flash("Contestant name is required.")
        return redirect(url_for("tinfoilhat.index"))
    
    db = get_db()
    db.execute(
        "INSERT INTO contestant (name, phone_number, email, notes) VALUES (?, ?, ?, ?)",
        (name, phone_number, email, notes)
    )
    db.commit()
    
    flash(f"Contestant '{name}' added successfully.")
    return redirect(url_for("tinfoilhat.index"))


@bp.route("/test/baseline", methods=["POST"])
def start_baseline():
    """
    Start the baseline test.
    
    :return: JSON response with baseline data
    :rtype: Response
    """
    # Get baseline readings from HackRF
    baseline_data = scanner.get_baseline_readings()
    
    # Store in session for later use
    current_app.config["CURRENT_BASELINE"] = baseline_data
    
    # Return the data for visualization
    return jsonify({
        "status": "success",
        "message": f"Baseline test completed with {scanner.samples_per_freq} samples per frequency.",
        "data": {
            "frequencies": scanner.frequencies,
            "baseline": baseline_data,
            "samples_per_frequency": scanner.samples_per_freq
        }
    })


@bp.route("/test/measure", methods=["POST"])
def measure_hat():
    """
    Measure a hat's attenuation after baseline has been established.
    
    :return: JSON response with test results
    :rtype: Response
    """
    # Get the baseline data from config
    baseline_data = current_app.config.get("CURRENT_BASELINE")
    if not baseline_data:
        return jsonify({
            "status": "error",
            "message": "Baseline test has not been run. Please run baseline first."
        }), 400
    
    # Get contestant ID from form
    contestant_id = request.form.get("contestant_id")
    if not contestant_id:
        return jsonify({
            "status": "error",
            "message": "Contestant ID is required."
        }), 400
    
    # Get hat measurements from HackRF
    hat_data = scanner.get_hat_readings()
    
    # Calculate attenuation
    attenuation_data = scanner.calculate_attenuation(baseline_data, hat_data)
    average_attenuation = sum(attenuation_data) / len(attenuation_data)
    
    # Save results to database
    db = get_db()
    
    # Add test result
    cursor = db.execute(
        """
        INSERT INTO test_result (contestant_id, average_attenuation)
        VALUES (?, ?)
        """,
        (contestant_id, average_attenuation)
    )
    test_result_id = cursor.lastrowid
    
    # Add individual frequency measurements
    for i, freq in enumerate(scanner.frequencies):
        db.execute(
            """
            INSERT INTO test_data 
            (test_result_id, frequency, baseline_level, hat_level, attenuation)
            VALUES (?, ?, ?, ?, ?)
            """,
            (test_result_id, freq, baseline_data[i], hat_data[i], attenuation_data[i])
        )
    
    # Check if this is the best score for this contestant
    best_score = db.execute(
        """
        SELECT MAX(average_attenuation) as best
        FROM test_result
        WHERE contestant_id = ?
        """,
        (contestant_id,)
    ).fetchone()["best"]
    
    # Update is_best_score flag
    if average_attenuation >= best_score:
        # Reset previous best scores
        db.execute(
            """
            UPDATE test_result
            SET is_best_score = 0
            WHERE contestant_id = ?
            """,
            (contestant_id,)
        )
        
        # Set this as the best score
        db.execute(
            """
            UPDATE test_result
            SET is_best_score = 1
            WHERE id = ?
            """,
            (test_result_id,)
        )
    
    db.commit()
    
    # Get the contestant name for the response
    contestant_name = db.execute(
        "SELECT name FROM contestant WHERE id = ?", 
        (contestant_id,)
    ).fetchone()["name"]
    
    # Return test results
    return jsonify({
        "status": "success",
        "message": f"Hat measurement completed with {scanner.samples_per_freq} samples per frequency.",
        "data": {
            "frequencies": scanner.frequencies,
            "baseline": baseline_data,
            "hat_measurements": hat_data,
            "attenuation": attenuation_data,
            "average_attenuation": average_attenuation,
            "is_best_score": average_attenuation >= best_score,
            "samples_per_frequency": scanner.samples_per_freq,
            "contestant_name": contestant_name
        }
    }) 