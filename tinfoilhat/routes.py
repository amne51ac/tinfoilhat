"""
Routes module for the Tinfoil Hat Competition application.

This module defines all HTTP endpoints for the Flask application.
"""

import contextlib
import json
import queue
import time
import traceback
from datetime import datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)

from tinfoilhat.db import get_db
from tinfoilhat.scanner import Scanner

bp = Blueprint("tinfoilhat", __name__, url_prefix="")

# Instead of creating the scanner at module level, create it for each request
# This will prevent issues when Flask reloads the application
scanner = None

# Global variable to track the latest frequency measurement
latest_frequency_measurement = None

# Dictionaries to store client queues for SSE streams
freq_clients = {}
billboard_clients = {}


# Add a custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        return json.JSONEncoder.default(self, obj)


@bp.route("/frequency-stream")
def frequency_stream():
    """
    Server-Sent Events (SSE) endpoint that streams real-time frequency measurements
    to the billboard. This allows the dashboard to update as each frequency is measured.

    :return: Event stream response
    :rtype: Response
    """

    def generate():
        global latest_frequency_measurement
        last_measurement_id = None

        while True:
            # If we have a new measurement since last time
            if latest_frequency_measurement and latest_frequency_measurement.get("id") != last_measurement_id:
                # Update the last sent ID
                last_measurement_id = latest_frequency_measurement.get("id")

                # Send the measurement data
                yield f"data: {json.dumps(latest_frequency_measurement, cls=DateTimeEncoder)}\n\n"

            # Sleep to avoid high CPU usage
            time.sleep(0.1)

    # Set appropriate headers for SSE
    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"  # Disable proxy buffering
    return response


# New functions for persistent storage of measurements
def store_measurement(measurement_type, frequency_hz, power):
    """
    Store a measurement in the database for persistence between app restarts.

    :param measurement_type: Type of measurement ('baseline' or 'hat')
    :type measurement_type: str
    :param frequency_hz: Frequency in Hz
    :type frequency_hz: int
    :param power: Power measurement in dBm
    :type power: float
    """
    db = get_db()

    # Check if measurement exists
    existing = db.execute(
        "SELECT id FROM measurement_cache WHERE type = ? AND frequency = ?", (measurement_type, frequency_hz)
    ).fetchone()

    if existing:
        # Update existing measurement
        db.execute("UPDATE measurement_cache SET power = ? WHERE id = ?", (power, existing["id"]))
    else:
        # Insert new measurement
        db.execute(
            "INSERT INTO measurement_cache (type, frequency, power) VALUES (?, ?, ?)",
            (measurement_type, frequency_hz, power),
        )

    db.commit()

    # Also store in app config for current request
    if measurement_type == "baseline":
        if "BASELINE_DATA" not in current_app.config:
            current_app.config["BASELINE_DATA"] = {}
        current_app.config["BASELINE_DATA"][str(int(frequency_hz))] = power
    else:  # hat
        if "HAT_DATA" not in current_app.config:
            current_app.config["HAT_DATA"] = {}
        current_app.config["HAT_DATA"][str(int(frequency_hz))] = power


def get_measurements(measurement_type):
    """
    Get all measurements of a specific type from the database.

    :param measurement_type: Type of measurement ('baseline' or 'hat')
    :type measurement_type: str
    :return: Dictionary of frequency -> power
    :rtype: dict
    """
    db = get_db()
    measurements = db.execute(
        "SELECT frequency, power FROM measurement_cache WHERE type = ?", (measurement_type,)
    ).fetchall()

    result = {}
    for row in measurements:
        result[str(int(row["frequency"]))] = row["power"]

    return result


def load_measurements_to_config():
    """
    Load measurements from database into application config.
    Call this at the start of relevant routes to ensure we have current data.
    """
    baseline_data = get_measurements("baseline")
    hat_data = get_measurements("hat")

    if baseline_data:
        current_app.config["BASELINE_DATA"] = baseline_data

    if hat_data:
        current_app.config["HAT_DATA"] = hat_data


def clear_measurements():
    """
    Clear all measurements from the database.
    Call this after test results have been saved.
    """
    db = get_db()
    db.execute("DELETE FROM measurement_cache")
    db.commit()

    # Also clear from app config
    if "BASELINE_DATA" in current_app.config:
        del current_app.config["BASELINE_DATA"]
    if "HAT_DATA" in current_app.config:
        del current_app.config["HAT_DATA"]


def get_scanner():
    """
    Get or create a scanner instance.

    This lazy-loads the scanner only when needed and helps with app reloading.

    :return: Scanner instance
    :rtype: Scanner
    """
    global scanner
    if scanner is None:
        try:
            # Attempt to initialize scanner with the HackRF device
            print("Initializing Scanner with HackRF device...")
            scanner = Scanner(samples_per_freq=1000)  # Take 3 samples per frequency for more accurate measurements

            # Check if HackRF is actually available
            if not scanner.hackrf_available:
                print("Scanner initialized but HackRF is not available")
                scanner = None
                return None

            print("Scanner successfully initialized with HackRF")
        except Exception as e:
            current_app.logger.error(f"Error initializing Scanner: {str(e)}")
            scanner = None
            return None
    return scanner


# Instead of using before_app_first_request on Blueprint, we'll clear the scanner
# each time a specific endpoint is accessed
@bp.before_request
def clear_scanner_if_needed():
    """
    Reset the scanner when needed.
    This function checks if we need to reinitialize the scanner.
    """
    global scanner

    # Only clear the scanner if it already exists but appears unhealthy
    if scanner is not None and not getattr(scanner, "hackrf_available", False):
        print("Existing scanner detected but HackRF is not available. Clearing scanner.")
        scanner = None


@bp.route("/", methods=["GET"])
def index():
    """
    Main application page with leaderboard and test controls.

    :return: Rendered template for the main page
    :rtype: str
    """
    # Force scanner initialization to check HackRF on app startup
    global scanner
    if scanner is None:
        scanner = get_scanner()

    # Load any cached measurements into the app config
    load_measurements_to_config()

    # Get hat_type filter parameter
    hat_type = request.args.get("hat_type")

    # Get leaderboard data - only the best scores per contestant
    db = get_db()

    # Build the query based on filter
    query = """
        SELECT c.name, t.average_attenuation, t.test_date, t.hat_type
        FROM contestant c
        JOIN test_result t ON c.id = t.contestant_id
        WHERE t.is_best_score = 1
    """

    # Add hat_type filter if provided
    params = []
    if hat_type and hat_type.lower() in ["classic", "hybrid"]:
        query += " AND t.hat_type = ?"
        params.append(hat_type.lower())

    # Add order by clause
    query += " ORDER BY t.average_attenuation DESC"

    # Execute the query
    leaderboard = db.execute(query, params).fetchall()

    # Get all contestants for the dropdown
    contestants = db.execute("SELECT id, name FROM contestant").fetchall()

    return render_template("index.html", leaderboard=leaderboard, contestants=contestants, active_filter=hat_type)


@bp.route("/leaderboard", methods=["GET"])
def get_leaderboard():
    """
    API endpoint to fetch the current leaderboard data.

    :return: JSON response with leaderboard data and contestants list
    :rtype: Response
    """
    # Get hat_type filter parameter
    hat_type = request.args.get("hat_type")
    # Get show_all_types parameter
    show_all_types = request.args.get("show_all_types") == "true"

    db = get_db()

    # Build the query based on filter
    if show_all_types and not hat_type:
        # Show both classic and hybrid best scores for each contestant
        query = """
            SELECT c.name, t.average_attenuation, t.test_date, t.hat_type
            FROM contestant c
            JOIN (
                SELECT contestant_id, MAX(average_attenuation) as max_att, hat_type
                FROM test_result
                GROUP BY contestant_id, hat_type
            ) best_scores ON c.id = best_scores.contestant_id
            JOIN test_result t ON c.id = t.contestant_id
                AND t.average_attenuation = best_scores.max_att
                AND t.hat_type = best_scores.hat_type
            ORDER BY t.average_attenuation DESC
        """
        params = []
    elif hat_type and hat_type.lower() in ["classic", "hybrid"]:
        # Show best scores for the selected hat type for each contestant
        query = """
            SELECT c.name, t.average_attenuation, t.test_date, t.hat_type
            FROM contestant c
            JOIN (
                SELECT contestant_id, MAX(average_attenuation) as max_att
                FROM test_result
                WHERE hat_type = ?
                GROUP BY contestant_id
            ) best_scores ON c.id = best_scores.contestant_id
            JOIN test_result t ON c.id = t.contestant_id
                AND t.average_attenuation = best_scores.max_att
                AND t.hat_type = ?
            ORDER BY t.average_attenuation DESC
        """
        params = [hat_type.lower(), hat_type.lower()]
    else:
        # Original query - showing only best scores regardless of hat type
        query = """
            SELECT c.name, t.average_attenuation, t.test_date, t.hat_type
            FROM contestant c
            JOIN test_result t ON c.id = t.contestant_id
            WHERE t.is_best_score = 1
            ORDER BY t.average_attenuation DESC
        """
        params = []

    # Execute the query
    leaderboard = db.execute(query, params).fetchall()

    # Convert to list of dictionaries for JSON serialization
    leaderboard_data = []
    for i, row in enumerate(leaderboard):
        leaderboard_data.append(
            {
                "rank": i + 1,
                "name": row["name"],
                "average_attenuation": row["average_attenuation"],
                "test_date": row["test_date"],
                "hat_type": row["hat_type"] or "classic",  # Default to 'classic' if NULL
            }
        )

    # Get all contestants for the dropdown
    contestants = db.execute("SELECT id, name FROM contestant").fetchall()

    # Convert to list of dictionaries for JSON serialization
    contestants_data = []
    for row in contestants:
        contestants_data.append(
            {
                "id": row["id"],
                "name": row["name"],
            }
        )

    return jsonify({"leaderboard": leaderboard_data, "contestants": contestants_data})


@bp.route("/contestants", methods=["POST"])
def add_contestant():
    """
    Add a new contestant.

    :return: Redirect or JSON response based on request type
    :rtype: Response
    """
    name = request.form.get("name")
    phone_number = request.form.get("phone_number", "")
    email = request.form.get("email", "")
    notes = request.form.get("notes", "")

    if not name:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "error", "message": "Contestant name is required."}), 400
        flash("Contestant name is required.")
        return redirect(url_for("tinfoilhat.index"))

    # Check for duplicate contestant names
    db = get_db()
    existing_contestant = db.execute("SELECT id FROM contestant WHERE name = ?", (name,)).fetchone()

    if existing_contestant:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "error", "message": f"A contestant with the name '{name}' already exists."}), 400
        flash(f"A contestant with the name '{name}' already exists.")
        return redirect(url_for("tinfoilhat.index"))

    cursor = db.execute(
        "INSERT INTO contestant (name, phone_number, email, notes) VALUES (?, ?, ?, ?)",
        (name, phone_number, email, notes),
    )
    db.commit()

    # Get the ID of the newly inserted contestant
    new_contestant_id = cursor.lastrowid

    # Check if this is an AJAX request
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            {
                "status": "success",
                "message": f"Contestant '{name}' added successfully.",
                "contestant": {"id": new_contestant_id, "name": name},
            }
        )

    # For traditional form submissions
    flash(f"Contestant '{name}' added successfully.")
    return redirect(url_for("tinfoilhat.index"))


@bp.route("/test/baseline", methods=["POST"])
def start_baseline():
    """
    Start the baseline test.

    :return: JSON response with baseline data
    :rtype: Response
    """
    global latest_frequency_measurement

    try:
        print("\n" + "=" * 80)
        print("*** NEW BASELINE TEST STARTING - CLEARING ALL PREVIOUS TEST DATA ***")
        print("=" * 80)

        # First, call the force reset endpoint to immediately clear all displays
        # This is a backup mechanism to ensure we reset even if SSE fails
        try:
            force_reset_all_displays()
            print("RESET: Called force_reset_all_displays() to immediately reset all client displays")
        except Exception as e:
            print(f"Warning: force_reset_all_displays failed: {str(e)}")

        # Set a special short-lived global reset flag with high visibility timestamp
        # This will be picked up by polling clients and force them to reset immediately
        latest_frequency_measurement = {
            "id": f"force_reset_{time.time()}",
            "event_type": "clear_all",
            "timestamp": datetime.now(),
            "message": "IMMEDIATE RESET - New baseline test started",
            "priority": "high",
            "reset_required": True,
        }
        print("SET GLOBAL RESET FLAG: latest_frequency_measurement set to force reset")

        # First, explicitly clear all measurement data from the database
        db = get_db()
        db.execute("DELETE FROM measurement_cache")
        db.commit()
        print("DATABASE: Cleared all measurement data from database")

        # Second, explicitly clear all data from application memory
        for key in ["BASELINE_DATA", "HAT_DATA", "ATTENUATION_DATA", "CURRENT_BASELINE"]:
            if key in current_app.config:
                del current_app.config[key]
        print("MEMORY: Cleared all measurement data from application config")

        # Third, reset the test state to notify clients
        print("NOTIFICATION: Calling reset_test_state() to notify clients...")
        reset_test_state()
        print("NOTIFICATION: Completed reset_test_state()")

        # CRITICAL: Force clients to update their display with empty data
        print("\nCRITICAL: Sending FORCE CLEAR instructions to all clients")

        # Create and broadcast additional clear event with explicit CLEAR instruction
        clear_event = {
            "id": f"clear_all_{time.time()}",
            "event_type": "clear_all",
            "timestamp": datetime.now(),
            "message": "All test data has been cleared for new baseline test",
        }

        # Broadcast to all clients with high priority
        clear_count = 0
        print(f"Frequency Clients: {len(freq_clients)}")
        for client_id, client_queue in freq_clients.items():
            try:
                # Force clear event to front of queue
                old_queue_contents = list(client_queue.queue)
                client_queue.queue.clear()
                client_queue.put(clear_event)
                # Put old items back after clear event
                for old_item in old_queue_contents:
                    client_queue.put(old_item)
                clear_count += 1
                print(f"  - Sent clear to freq client {client_id[:8]}...")
            except Exception as e:
                print(f"  - Failed to send clear event to freq client {client_id[:8]}: {str(e)}")

        print(f"Billboard Clients: {len(billboard_clients)}")
        for client_id, client_queue in billboard_clients.items():
            try:
                # Force clear event to front of queue
                old_queue_contents = list(client_queue.queue)
                client_queue.queue.clear()
                client_queue.put(clear_event)
                # Put old items back after clear event
                for old_item in old_queue_contents:
                    client_queue.put(old_item)
                clear_count += 1
                print(f"  - Sent clear to billboard client {client_id[:8]}...")
            except Exception as e:
                print(f"  - Failed to send clear event to billboard client {client_id[:8]}: {str(e)}")

        print(f"CRITICAL: Sent force clear events to {clear_count} clients")

        # Set global latest measurement to clear event
        latest_frequency_measurement = clear_event
        print("GLOBAL: Updated latest_frequency_measurement with clear event")

        # Send additional empty spectrum data to force chart reset
        empty_spectrum = {
            "event_type": "billboard_update",
            "timestamp": datetime.now(),
            "spectrum_data": {
                "frequencies": [],
                "baseline_levels": [],
                "hat_levels": [],
                "attenuations": [],
                "test_state": "reset",
                "timestamp": time.time(),
            },
        }

        # Broadcast empty spectrum to all billboard clients
        empty_count = 0
        print("\nCRITICAL: Sending empty spectrum data")
        for client_id, client_queue in billboard_clients.items():
            try:
                client_queue.put(empty_spectrum)
                empty_count += 1
                print(f"  - Sent empty spectrum to billboard client {client_id[:8]}...")
            except Exception as e:
                print(f"  - Failed to send empty spectrum to billboard client {client_id[:8]}: {str(e)}")

        print(f"CRITICAL: Sent empty spectrum data to {empty_count} billboard clients")

        # Very important: longer delay to allow clients to process the clear events
        # This ensures clients have time to process events before they see new frequencies
        print("\nDELAY: Waiting for clients to process clear events...")
        time.sleep(0.5)  # 500ms delay
        print("DELAY: Completed waiting period")

        print("NOTIFICATION: All clear events sent to all connected clients")
        print("=" * 80 + "\n")

        # Get scanner instance
        print("SCANNER: Initializing scanner...")
        scanner = get_scanner()
        if scanner is None:
            print("ERROR: Scanner initialization failed")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Scanner initialization failed. Please check HackRF device connection.",
                    }
                ),
                500,
            )

        # Return the frequencies to test
        frequencies = [float(f) for f in scanner.frequencies]
        print(f"SCANNER: Initialized baseline test with {len(frequencies)} frequencies")
        print("=" * 80)
        print("*** BASELINE TEST READY - ALL PREVIOUS DATA CLEARED ***")
        print("=" * 80 + "\n")

        return jsonify(
            {
                "status": "success",
                "message": "Baseline test started - all previous data cleared",
                "data": {
                    "frequencies": frequencies,
                    "frequency_count": len(frequencies),
                },
            }
        )
    except Exception as e:
        print(f"ERROR starting baseline test: {str(e)}")
        traceback.print_exc()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Failed to start baseline test: {str(e)}",
                }
            ),
            500,
        )


@bp.route("/test/measure", methods=["POST"])
def measure_hat():
    """
    Start the hat measurement test.

    :return: JSON response with hat data
    :rtype: Response
    """
    try:
        print("\n" + "=" * 80)
        print("HAT MEASUREMENT REQUESTED - CHECKING FOR VALID BASELINE DATA")

        # Don't reset - we need to keep the baseline data
        # But do ensure we clear any previous hat data before starting a new hat measurement
        if "HAT_DATA" in current_app.config:
            del current_app.config["HAT_DATA"]
            print("Cleared previous HAT_DATA from memory")

        if "ATTENUATION_DATA" in current_app.config:
            del current_app.config["ATTENUATION_DATA"]
            print("Cleared previous ATTENUATION_DATA from memory")

        # Make sure we have baseline data and it's valid
        if "BASELINE_DATA" not in current_app.config or not current_app.config["BASELINE_DATA"]:
            error_msg = "Baseline data not found. Please run the baseline test first."
            print(f"ERROR: {error_msg}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": error_msg,
                    }
                ),
                400,
            )

        # Check that we have a reasonable amount of baseline data
        baseline_count = len(current_app.config["BASELINE_DATA"])
        if baseline_count < 5:  # At least 5 frequency measurements
            error_msg = (
                f"Insufficient baseline data ({baseline_count} frequencies). Please run a complete baseline test."
            )
            print(f"ERROR: {error_msg}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": error_msg,
                    }
                ),
                400,
            )

        # Get scanner instance
        scanner = get_scanner()
        if scanner is None:
            print("ERROR: Scanner initialization failed")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Scanner initialization failed. Please check HackRF device connection.",
                    }
                ),
                500,
            )

        # Get the baseline data keys (frequency Hz values)
        baseline_frequencies = [int(freq_key) for freq_key in current_app.config["BASELINE_DATA"]]
        frequencies = [float(freq_hz) / 1e6 for freq_hz in baseline_frequencies]  # Convert to MHz

        print(f"Starting hat measurement with {len(frequencies)} frequencies from baseline data")
        print("=" * 80 + "\n")

        return jsonify(
            {
                "status": "success",
                "message": "Hat measurement started",
                "data": {
                    "frequencies": frequencies,
                    "frequency_count": len(frequencies),
                },
            }
        )
    except Exception as e:
        print(f"Error starting hat measurement: {str(e)}")
        traceback.print_exc()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Failed to start hat measurement: {str(e)}",
                }
            ),
            500,
        )


@bp.route("/test/measure_frequency", methods=["POST"])
def measure_frequency():
    """
    API endpoint to measure power at a specific frequency.
    This can be used for both baseline and hat measurements.

    Required parameters:
    - frequency: Frequency in MHz to measure
    - measurement_type: 'baseline' or 'hat'

    :return: JSON response with measurement data
    :rtype: Response
    """
    global latest_frequency_measurement

    # Get scanner instance
    scanner = get_scanner()
    if scanner is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Scanner initialization failed. Please check HackRF device connection.",
                }
            ),
            500,
        )

    # Get parameters from request
    frequency = request.json.get("frequency")
    measurement_type = request.json.get("measurement_type")  # 'baseline' or 'hat'

    if not frequency:
        return (
            jsonify({"status": "error", "message": "Frequency parameter is required."}),
            400,
        )

    if not measurement_type or measurement_type not in ["baseline", "hat"]:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Valid measurement_type parameter ('baseline' or 'hat') is required.",
                }
            ),
            400,
        )

    try:
        # Convert frequency to number if it's a string
        freq_mhz = float(frequency)

        # Convert MHz to Hz for the HackRF device
        freq_hz = freq_mhz * 1e6

        # Validate frequency is within HackRF's supported range (1 MHz to 6 GHz)
        if freq_hz < 1e6 or freq_hz > 6e9:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Frequency {freq_mhz} MHz is outside supported range (1 MHz to 6 GHz).",
                    }
                ),
                400,
            )

        # Perform the measurement using Hz value
        power = scanner._measure_power_at_frequency(freq_hz)

        # Save the measurement to app config and database
        if measurement_type == "baseline":
            print(f"DEBUG - Stored baseline for {freq_mhz} MHz: {power} dBm with key {str(int(freq_hz))}")
            store_measurement("baseline", int(freq_hz), power)
        else:
            print(f"DEBUG - Stored hat for {freq_mhz} MHz: {power} dBm with key {str(int(freq_hz))}")
            store_measurement("hat", int(freq_hz), power)

        # Calculate attenuation if we have both baseline and hat measurements for this frequency
        attenuation = None
        freq_key = str(int(freq_hz))  # Consistent key format
        if (
            measurement_type == "hat"
            and "BASELINE_DATA" in current_app.config
            and freq_key in current_app.config["BASELINE_DATA"]
        ):
            baseline_power = current_app.config["BASELINE_DATA"][freq_key]
            attenuation = baseline_power - power  # Allow negative attenuation values
            print(
                f"DEBUG - Calculated attenuation for {freq_mhz} MHz: {attenuation} dB "
                f"(baseline: {baseline_power} dBm, hat: {power} dBm)"
            )

        # Create a measurement data object
        measurement_data = {
            "id": f"{int(freq_hz)}_{measurement_type}_{time.time()}",  # Create a unique ID
            "frequency_mhz": freq_mhz,
            "frequency_hz": freq_hz,
            "power": power,
            "measurement_type": measurement_type,
            "timestamp": datetime.now(),
        }

        # Add attenuation if available
        if attenuation is not None:
            measurement_data["attenuation"] = attenuation
            measurement_data["baseline_power"] = baseline_power

        # Get the contestant ID if it's available in the session
        if request.json.get("contestant_id"):
            measurement_data["contestant_id"] = request.json.get("contestant_id")

            # Get contestant name and hat type if contestant_id is provided
            if measurement_type == "hat":
                try:
                    db = get_db()
                    contestant = db.execute(
                        "SELECT name FROM contestant WHERE id = ?", (request.json.get("contestant_id"),)
                    ).fetchone()

                    if contestant:
                        measurement_data["contestant_name"] = contestant["name"]
                        # Use the hat_type from the request if available, otherwise use from database
                        measurement_data["hat_type"] = request.json.get("hat_type", "classic")
                except Exception as e:
                    current_app.logger.error(f"Error fetching contestant info: {str(e)}")

        # Update the global variable to notify SSE clients
        latest_frequency_measurement = measurement_data

        # Return the measurement results
        return jsonify(
            {
                "status": "success",
                "data": {
                    "frequency": freq_hz,
                    "power": power,
                    "measurement_type": measurement_type,
                    "attenuation": attenuation,
                },
            }
        )

    except RuntimeError as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"HackRF device error: {str(e)}. Please reconnect your device and try again.",
                }
            ),
            500,
        )
    except Exception as e:
        current_app.logger.error(f"Error in frequency measurement: {str(e)}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"An unexpected error occurred: {str(e)}",
                }
            ),
            500,
        )


@bp.route("/test/save_results", methods=["POST"])
def save_results():
    """
    API endpoint to save the final test results to the database.
    This should be called after all measurements have been completed.

    All calculations are performed server-side:
    - Only valid measurements (frequencies with both baseline and hat data) are used
    - Average attenuation is calculated from these valid measurements
    - Frequency band effectiveness values are determined based on standard RF bands
    - The database stores only the valid measurements for future reference

    The client receives and displays the calculated values without performing any calculations.

    Required parameters:
    - contestant_id: ID of the contestant

    :return: JSON response with test results
    :rtype: Response
    """
    global latest_frequency_measurement

    # Get the baseline and hat data from config
    baseline_data = current_app.config.get("BASELINE_DATA", {})
    hat_data = current_app.config.get("HAT_DATA", {})

    if not baseline_data or not hat_data:
        error_msg = "Baseline or hat measurements have not been completed."

        # Add more detailed error information
        if not baseline_data:
            error_msg += " Baseline data is missing."
        if not hat_data:
            error_msg += " Hat measurement data is missing."

        error_msg += " Please run both tests first."

        # Debug log what data we have
        print(f"DEBUG - Save failed - Baseline data: {baseline_data}")
        print(f"DEBUG - Save failed - Hat data: {hat_data}")

        return (
            jsonify(
                {
                    "status": "error",
                    "message": error_msg,
                }
            ),
            400,
        )

    # Get contestant ID from form
    contestant_id = request.json.get("contestant_id")
    if not contestant_id:
        return (
            jsonify({"status": "error", "message": "Contestant ID is required."}),
            400,
        )

    # Get scanner to access frequencies list
    scanner = get_scanner()
    if scanner is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Scanner initialization failed. Please check HackRF device connection.",
                }
            ),
            500,
        )

    try:
        # Convert stored data to ordered lists matching scanner.frequencies
        baseline_readings = []
        hat_readings = []
        valid_measurements = [False]  # Initialize with at least one element for safe sum() call
        missing_frequencies = []

        # Initialize variables that might be needed outside this try block
        frequencies_mhz = []
        attenuation_data = []
        test_result_id = None  # Initialize test_result_id to None
        average_attenuation = 0.0  # Default average attenuation

        # Initialize effectiveness values to defaults
        effectiveness = {"hf_band": 0.0, "vhf_band": 0.0, "uhf_band": 0.0, "shf_band": 0.0}

        # Initialize min/max attenuation values
        max_attenuation = 0.0
        max_attenuation_freq = 0.0
        min_attenuation = 0.0
        min_attenuation_freq = 0.0

        # Debug: Print stored data
        print("DEBUG - Baseline data in config:", current_app.config.get("BASELINE_DATA", {}))
        print("DEBUG - Hat data in config:", current_app.config.get("HAT_DATA", {}))

        for freq in scanner.frequencies:
            freq_hz = freq * 1e6  # Convert MHz to Hz
            str_freq = str(int(freq_hz))  # Use full Hz frequency as key

            # Debug: Print what we're looking for
            print(f"DEBUG - Looking for frequency {freq} MHz ({str_freq} Hz)")

            baseline_found = str_freq in baseline_data
            hat_found = str_freq in hat_data

            if baseline_found and hat_found:
                baseline_readings.append(baseline_data[str_freq])
                hat_readings.append(hat_data[str_freq])
                valid_measurements.append(True)
                print(f"DEBUG - Found both: Baseline={baseline_data[str_freq]}, Hat={hat_data[str_freq]}")
            else:
                missing_frequencies.append(freq)
                # Use placeholder values if measurements are missing
                baseline_readings.append(-80.0)
                hat_readings.append(-80.0)
                valid_measurements.append(False)
                print(f"DEBUG - Missing data: baseline_found={baseline_found}, hat_found={hat_found}")

        # Debug: Print constructed measurement arrays
        print("DEBUG - Baseline readings:", baseline_readings)
        print("DEBUG - Hat readings:", hat_readings)

        # Calculate attenuation
        attenuation_data = scanner.calculate_attenuation(baseline_readings, hat_readings)

        # Calculate average using only valid measurements
        total_attenuation = 0
        valid_count = 0
        for i, att in enumerate(attenuation_data):
            if valid_measurements[i]:
                total_attenuation += att
                valid_count += 1

        average_attenuation = float(total_attenuation / valid_count) if valid_count > 0 else 0.0
        print(f"DEBUG - Calculated average using only valid measurements: {average_attenuation}")

        # Calculate effectiveness for different frequency bands using standard RF band names
        # Only include valid measurements in these calculations
        hf_values = [
            attenuation_data[i] for i, f in enumerate(scanner.frequencies) if 2 <= f < 30 and valid_measurements[i]
        ]  # HF: 2-30 MHz
        vhf_values = [
            attenuation_data[i] for i, f in enumerate(scanner.frequencies) if 30 <= f < 300 and valid_measurements[i]
        ]  # VHF: 30-300 MHz
        uhf_values = [
            attenuation_data[i] for i, f in enumerate(scanner.frequencies) if 300 <= f < 3000 and valid_measurements[i]
        ]  # UHF: 300 MHz - 3 GHz
        shf_values = [
            attenuation_data[i]
            for i, f in enumerate(scanner.frequencies)
            if 3000 <= f <= 5900 and valid_measurements[i]
        ]  # SHF: 3-30 GHz

        effectiveness = {
            "hf_band": float(sum(hf_values) / len(hf_values)) if hf_values else 0.0,
            "vhf_band": float(sum(vhf_values) / len(vhf_values)) if vhf_values else 0.0,
            "uhf_band": float(sum(uhf_values) / len(uhf_values)) if uhf_values else 0.0,
            "shf_band": float(sum(shf_values) / len(shf_values)) if shf_values else 0.0,
        }

        # Find peak and minimum attenuation (only consider valid measurements)
        valid_attenuation_with_idx = [
            (i, att) for i, (att, valid) in enumerate(zip(attenuation_data, valid_measurements)) if valid
        ]

        if valid_attenuation_with_idx:
            max_idx, max_att = max(valid_attenuation_with_idx, key=lambda x: x[1])
            min_idx, min_att = min(valid_attenuation_with_idx, key=lambda x: x[1])

            max_attenuation = float(max_att)
            max_attenuation_freq = float(scanner.frequencies[max_idx])

            min_attenuation = float(min_att)
            min_attenuation_freq = float(scanner.frequencies[min_idx])
        else:
            # Default values if no valid measurements
            max_attenuation = 0.0
            max_attenuation_freq = 0.0
            min_attenuation = 0.0
            min_attenuation_freq = 0.0

        # Save results to database
        db = get_db()

        # Get hat type from request
        hat_type = request.json.get("hat_type", "classic")

        # Check if this is the best score for this contestant BEFORE inserting the new result
        # BUT make sure we only compare against scores of the same hat type
        best_score_result = db.execute(
            """
            SELECT COUNT(*) as count, MAX(average_attenuation) as best
            FROM test_result
            WHERE contestant_id = ? AND hat_type = ?
            """,
            (contestant_id, hat_type),
        ).fetchone()

        # Check if the contestant has any previous entries of this hat type
        has_previous_entries = best_score_result and best_score_result["count"] > 0

        # First score for this hat type is always the best
        # Otherwise, compare with previous best for this hat type
        previous_best_score = best_score_result["best"] if has_previous_entries else None
        is_best = not has_previous_entries or (has_previous_entries and average_attenuation > previous_best_score)

        # Add test result
        cursor = db.execute(
            """
            INSERT INTO test_result (contestant_id, average_attenuation, is_best_score, hat_type)
            VALUES (?, ?, ?, ?)
            """,
            (contestant_id, average_attenuation, 1 if is_best else 0, hat_type),
        )
        test_result_id = cursor.lastrowid

        # Add individual frequency measurements
        for i, freq in enumerate(scanner.frequencies):
            # Only insert valid measurements
            if valid_measurements[i]:
                db.execute(
                    """
                    INSERT INTO test_data
                    (test_result_id, frequency, baseline_level, hat_level, attenuation)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        test_result_id,
                        float(freq),
                        float(baseline_readings[i]),
                        float(hat_readings[i]),
                        float(attenuation_data[i]),
                    ),
                )

        # If this is the best score, reset previous best scores
        if is_best:
            # Reset previous best scores (exclude the one we just added)
            db.execute(
                """
                UPDATE test_result
                SET is_best_score = 0
                WHERE contestant_id = ? AND id != ? AND hat_type = ?
                """,
                (contestant_id, test_result_id, hat_type),
            )

        db.commit()

        # Get the contestant name for the response
        contestant_result = db.execute("SELECT name FROM contestant WHERE id = ?", (contestant_id,)).fetchone()
        contestant_name = contestant_result["name"] if contestant_result else "Unknown"

        # Prepare a message about the score
        if average_attenuation < 0:
            score_message = (
                f"Warning: The hat shows negative attenuation ({average_attenuation:.2f} dB), "
                f"which means it's amplifying signals instead of blocking them."
            )
            if is_best:
                score_message += f" This is still your best {hat_type} score so far."
            else:
                score_message += f" Your previous best {hat_type} score of {previous_best_score:.2f} dB is better."
        else:
            if is_best:
                score_message = (
                    f"This is the best {hat_type} score for {contestant_name} "
                    f"with an attenuation of {average_attenuation:.2f} dB."
                )
            else:
                score_message = (
                    f"Not the best {hat_type} score for {contestant_name}. Previous best: "
                    f"{previous_best_score:.2f} dB, Current: {average_attenuation:.2f} dB."
                )

        # Clear stored data to prevent contaminating future tests
        clear_measurements()

        # After the test results are saved to the database, emit a test_complete event
        # with the same test_result_id from the saved test results
        try:
            db = get_db()

            # Retrieve the test result ID and data from the database
            test_result = db.execute(
                """
                SELECT id, date, average_attenuation
                FROM test_result
                WHERE contestant_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (contestant_id,),
            ).fetchone()

            if not test_result:
                print("Warning: Could not find the saved test result")
            else:
                test_result_id = test_result["id"]

                # Get the contestant info with a default for hat_type in case it's NULL
                contestant = db.execute(
                    """
                    SELECT c.name, COALESCE(t.hat_type, 'classic') as hat_type
                    FROM contestant c
                    JOIN test_result t ON c.id = t.contestant_id
                    WHERE c.id = ? AND t.id = ?
                    """,
                    (contestant_id, test_result_id),
                ).fetchone()

                # Get the test data points for this test result
                test_data_points = db.execute(
                    """
                    SELECT frequency, baseline_level, hat_level, attenuation
                    FROM test_data
                    WHERE test_result_id = ?
                    ORDER BY frequency
                    """,
                    (test_result_id,),
                ).fetchall()

                # Extract frequencies and attenuations from the test data
                frequencies_mhz = [point["frequency"] for point in test_data_points]
                attenuations = [point["attenuation"] for point in test_data_points]

                # Calculate effectiveness for different frequency bands using standard RF band names
                hf_values = [attenuations[i] for i, f in enumerate(frequencies_mhz) if 2 <= f < 30]  # HF: 2-30 MHz
                vhf_values = [
                    attenuations[i] for i, f in enumerate(frequencies_mhz) if 30 <= f < 300
                ]  # VHF: 30-300 MHz
                uhf_values = [
                    attenuations[i] for i, f in enumerate(frequencies_mhz) if 300 <= f < 3000
                ]  # UHF: 300 MHz - 3 GHz
                shf_values = [
                    attenuations[i] for i, f in enumerate(frequencies_mhz) if 3000 <= f <= 5900
                ]  # SHF: 3-30 GHz

                # Calculate average for each band
                effectiveness = {
                    "hf_band": float(sum(hf_values) / len(hf_values)) if hf_values else 0.0,
                    "vhf_band": float(sum(vhf_values) / len(vhf_values)) if vhf_values else 0.0,
                    "uhf_band": float(sum(uhf_values) / len(uhf_values)) if uhf_values else 0.0,
                    "shf_band": float(sum(shf_values) / len(shf_values)) if shf_values else 0.0,
                }

                # Find peak and minimum attenuation
                if attenuations:
                    max_idx = attenuations.index(max(attenuations))
                    min_idx = attenuations.index(min(attenuations))

                    max_attenuation = {"value": attenuations[max_idx], "frequency": frequencies_mhz[max_idx]}

                    min_attenuation = {"value": attenuations[min_idx], "frequency": frequencies_mhz[min_idx]}
                else:
                    max_attenuation = {"value": 0.0, "frequency": 0.0}
                    min_attenuation = {"value": 0.0, "frequency": 0.0}

                # Create a complete test data summary
                test_complete_data = {
                    "event_type": "test_complete",
                    "id": f"test_complete_{time.time()}",
                    "test_result_id": test_result_id,
                    "contestant_id": contestant_id,
                    "contestant_name": contestant["name"],
                    "hat_type": contestant["hat_type"],
                    "timestamp": datetime.now(),
                    "average_attenuation": test_result["average_attenuation"],
                    "frequencies": frequencies_mhz,
                    "attenuations": attenuations,
                    "effectiveness": effectiveness,
                    "max_attenuation": max_attenuation,
                    "min_attenuation": min_attenuation,
                }

                # Update the global variable to notify SSE clients of test completion
                latest_frequency_measurement = test_complete_data

        except Exception as e:
            print(f"Error emitting test_complete event: {str(e)}")
            # Continue with the normal response even if the event emission fails

        # Return the original success response
        return jsonify(
            {
                "status": "success",
                "message": score_message,
                "data": {
                    "test_result_id": test_result_id,
                    "average_attenuation": average_attenuation,
                    "valid_frequencies": sum(valid_measurements) if valid_measurements else 0,
                    "effectiveness": effectiveness,
                    "contestant_name": contestant_name,
                    "max_attenuation": {
                        "value": max_attenuation,
                        "frequency": max_attenuation_freq,
                    },
                    "min_attenuation": {
                        "value": min_attenuation,
                        "frequency": min_attenuation_freq,
                    },
                },
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error saving test results: {str(e)}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"An unexpected error occurred: {str(e)}",
                }
            ),
            500,
        )


@bp.route("/test/get_frequencies", methods=["GET"])
def get_frequencies():
    """
    API endpoint to get the list of frequencies to test.

    :return: JSON response with frequencies
    :rtype: Response
    """
    scanner = get_scanner()
    if scanner is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Scanner initialization failed. Please check HackRF device connection.",
                }
            ),
            500,
        )

    # Scanner.frequencies are in MHz in the initialization method,
    # but we need to return them in Hz to match our new code
    frequencies_hz = [int(freq * 1e6) for freq in scanner.frequencies]

    # Prepare frequency labels for the frontend
    frequency_labels = {}
    if hasattr(scanner, "frequency_labels"):
        for freq_mhz, label_data in scanner.frequency_labels.items():
            freq_hz = int(freq_mhz * 1e6)
            frequency_labels[str(freq_hz)] = {"name": label_data[0], "description": label_data[1]}

    return jsonify({"status": "success", "data": {"frequencies": frequencies_hz, "labels": frequency_labels}})


@bp.route("/billboard")
def billboard():
    """
    Display the billboard view showing leaderboards and recent test results

    :return: Rendered template
    :rtype: str
    """
    db = get_db()

    # Get most recent test result
    recent_test = db.execute(
        """
        SELECT t.id as max_id, c.name, t.hat_type, ROUND(t.average_attenuation, 2) as attenuation,
               t.test_date as date
        FROM test_result t
        JOIN contestant c ON t.contestant_id = c.id
        WHERE t.id = (SELECT MAX(id) FROM test_result)
    """
    ).fetchone()

    # Get leaderboard data
    leaderboard_classic = get_leaderboard_data("classic")
    leaderboard_hybrid = get_leaderboard_data("hybrid")

    # Get spectrum data for the most recent test
    spectrum_data = {}
    if recent_test and recent_test["max_id"]:
        test_data_points = db.execute(
            """
            SELECT frequency, baseline_level, hat_level, attenuation
            FROM test_data
            WHERE test_result_id = ?
            ORDER BY frequency
        """,
            (recent_test["max_id"],),
        ).fetchall()

        # Initialize these variables with empty lists before the conditional block
        frequencies = []
        baseline_levels = []
        hat_levels = []
        attenuations = []

        if test_data_points:
            frequencies = [round(point["frequency"] / 1e6, 2) for point in test_data_points]  # Convert to MHz
            baseline_levels = [point["baseline_level"] for point in test_data_points]
            hat_levels = [point["hat_level"] for point in test_data_points]
            attenuations = [point["attenuation"] for point in test_data_points]

            spectrum_data = {
                "frequencies": frequencies,
                "baseline_levels": baseline_levels,
                "hat_levels": hat_levels,
                "attenuations": attenuations,
            }

    # Get frequency labels from scanner
    frequency_labels = {}
    scanner = get_scanner()
    if scanner and hasattr(scanner, "frequency_labels"):
        frequency_labels = scanner.frequency_labels

    return render_template(
        "billboard.html",
        recent_test=recent_test,
        leaderboard_classic=leaderboard_classic,
        leaderboard_hybrid=leaderboard_hybrid,
        spectrum_data=spectrum_data,
        frequency_labels=frequency_labels,
    )


def get_leaderboard_data(hat_type):
    """
    Helper function to get leaderboard data for a specific hat type

    :param hat_type: Type of hat ('classic' or 'hybrid')
    :type hat_type: str
    :return: List of leaderboard entries
    :rtype: list
    """
    db = get_db()

    # Query for the best scores per contestant for this hat type
    results = db.execute(
        """
        SELECT c.name, ROUND(t.average_attenuation, 2) as attenuation
        FROM contestant c
        JOIN (
            SELECT contestant_id, MAX(average_attenuation) as max_att
            FROM test_result
            WHERE hat_type = ?
            GROUP BY contestant_id
        ) best_scores ON c.id = best_scores.contestant_id
        JOIN test_result t ON c.id = t.contestant_id
            AND t.average_attenuation = best_scores.max_att
            AND t.hat_type = ?
        ORDER BY t.average_attenuation DESC
        LIMIT 10
    """,
        (hat_type, hat_type),
    ).fetchall()

    # Convert to list of dictionaries
    return [{"name": result["name"], "attenuation": result["attenuation"]} for result in results]


@bp.route("/billboard-updates", methods=["GET"])
def billboard_updates():
    """
    Handle billboard updates either via SSE or polling.

    If request is from EventSource, setup SSE stream.
    Otherwise return JSON data for polling clients.

    Query Parameters:
    - last_id: Last event ID received (for polling)
    - force_clear: If 1, forces empty data with reset state (for troubleshooting)

    :return: SSE stream or JSON response
    :rtype: Response
    """
    is_sse = request.headers.get("accept") == "text/event-stream"
    last_id = request.args.get("last_id", 0, type=int)
    force_clear = request.args.get("force_clear", 0, type=int)

    # Check if this is a force clear request (for troubleshooting)
    if force_clear == 1:
        print("CRITICAL: Force clear request received - returning empty data")
        return jsonify(
            {
                "last_id": last_id,
                "spectrum_data": {
                    "frequencies": [],
                    "baseline_levels": [],
                    "hat_levels": [],
                    "attenuations": [],
                    "test_state": "reset",
                    "timestamp": time.time(),
                },
                "message": "Chart data cleared by force_clear request",
            }
        )

    # Function to normalize numpy values to native Python types
    def normalize_value(val):
        """Convert numpy types to native Python types for JSON serialization."""
        if val is None:
            return None
        if hasattr(val, "item"):
            return val.item()
        return val

    if not is_sse:
        # This is a regular HTTP request, likely polling
        # Respond with JSON instead of SSE
        try:
            # Initialize reset flags
            reset_detected = False
            reset_message = None

            # MODIFICATION: Check for reset events first, before doing anything else
            # If latest_frequency_measurement indicates a reset, prioritize sending that
            if latest_frequency_measurement and latest_frequency_measurement.get("event_type") in [
                "test_reset",
                "clear_all",
            ]:
                # Check if this is a high-priority reset that absolutely must be handled
                if latest_frequency_measurement.get("reset_required", False):
                    print("⚠️ CRITICAL: Found mandatory reset event - forcing client reset")
                    return jsonify(
                        {
                            "last_id": last_id,
                            "reset_detected": True,
                            "reset_message": latest_frequency_measurement.get(
                                "message", "Mandatory test reset required"
                            ),
                            "spectrum_data": {
                                "frequencies": [],
                                "baseline_levels": [],
                                "hat_levels": [],
                                "attenuations": [],
                                "test_state": "reset",
                                "timestamp": time.time(),
                            },
                        }
                    )

                # Calculate how old the reset event is (in seconds)
                event_time = latest_frequency_measurement.get("timestamp")
                age_seconds = 0
                if isinstance(event_time, datetime):
                    age_seconds = (datetime.now() - event_time).total_seconds()

                # Only use reset events that are less than 10 seconds old to prevent
                # old reset events from continuously triggering
                if age_seconds < 10:
                    print(f"Found recent reset event ({age_seconds}s old) - sending reset signal to polling client")
                    return jsonify(
                        {
                            "last_id": last_id,
                            "message": latest_frequency_measurement.get("message", "Test reset detected"),
                            "spectrum_data": {
                                "frequencies": [],
                                "baseline_levels": [],
                                "hat_levels": [],
                                "attenuations": [],
                                "test_state": "reset",
                                "timestamp": time.time(),
                            },
                        }
                    )

            db = get_db()

            # Fetch new test results based on last_id
            new_results = db.execute(
                """
                SELECT t.id, t.test_date, t.average_attenuation, t.hat_type, c.name
                FROM test_result t
                JOIN contestant c ON t.contestant_id = c.id
                WHERE t.id > ?
                ORDER BY t.id DESC
                LIMIT 1
                """,
                (last_id,),
            ).fetchall()

            # Only get the most recent result
            new_test = None
            max_id = last_id

            if new_results:
                result = new_results[0]
                max_id = result["id"]

                # Format date for display
                result_date = format_datetime(result["test_date"])

                new_test = {
                    "max_id": result["id"],
                    "name": result["name"],
                    "hat_type": result["hat_type"],
                    "attenuation": result["average_attenuation"],
                    "date": result_date,
                }

                # Get spectrum data for this test
                spectrum_data = db.execute(
                    """
                    SELECT frequency, baseline_level, hat_level, attenuation
                    FROM test_data
                    WHERE test_result_id = ?
                    ORDER BY frequency
                    """,
                    (result["id"],),
                ).fetchall()

                # Send spectrum data only if we have a new test
                if spectrum_data:
                    frequencies = [row["frequency"] for row in spectrum_data]
                    baseline_levels = [row["baseline_level"] for row in spectrum_data]
                    hat_levels = [row["hat_level"] for row in spectrum_data]
                    attenuations = [row["attenuation"] for row in spectrum_data]

                    # For now, using simplified effectiveness calculation
                    # We'll update this with the actual calculation later
                    effectiveness = {"hf_band": 0.0, "vhf_band": 0.0, "uhf_band": 0.0, "shf_band": 0.0}

                    # Calculate band-specific effectiveness
                    valid_attens = [a for a in attenuations if a is not None]
                    sum(valid_attens) / len(valid_attens) if valid_attens else 0

                    # Get min/max attenuation
                    if valid_attens:
                        max_atten = max(valid_attens)
                        max_atten_idx = attenuations.index(max_atten)
                        max_atten_freq = frequencies[max_atten_idx]

                        min_atten = min(valid_attens)
                        min_atten_idx = attenuations.index(min_atten)
                        min_atten_freq = frequencies[min_atten_idx]
                    else:
                        max_atten = 0
                        max_atten_freq = 0
                        min_atten = 0
                        min_atten_freq = 0

            # Get leaderboard data for each hat type
            leaderboard_classic = get_leaderboard_data("classic")
            leaderboard_hybrid = get_leaderboard_data("hybrid")

            # If we have active measurements, use those first (these are the measurements in progress)
            if "BASELINE_DATA" in current_app.config and current_app.config["BASELINE_DATA"]:
                baseline_data = current_app.config.get("BASELINE_DATA", {})
                hat_data = current_app.config.get("HAT_DATA", {})
                attenuation_data = current_app.config.get("ATTENUATION_DATA", {})

                # Get frequency lists (convert from string keys to float values)
                try:
                    # Determine test state first to properly structure the response
                    test_state = "baseline_only"
                    if hat_data:
                        test_state = "baseline_and_hat"

                    # Make a sorted list of all unique frequencies
                    all_frequencies = sorted([int(freq) for freq in set(baseline_data.keys()) | set(hat_data.keys())])

                    if all_frequencies:
                        frequencies = [round(freq / 1e6, 2) for freq in all_frequencies]  # Convert to MHz for display
                        baseline_levels = [
                            normalize_value(baseline_data.get(str(freq), None)) for freq in all_frequencies
                        ]
                        hat_levels = [normalize_value(hat_data.get(str(freq), None)) for freq in all_frequencies]
                        attenuations = [
                            normalize_value(attenuation_data.get(str(freq), None)) for freq in all_frequencies
                        ]

                        # Calculate effectiveness for different frequency bands
                        effectiveness = {"hf_band": 0.0, "vhf_band": 0.0, "uhf_band": 0.0, "shf_band": 0.0}

                        # Only calculate effectiveness if we have hat measurements
                        if hat_data:
                            # Get valid attenuation values for each band
                            hf_band = [
                                att for i, att in enumerate(attenuations) if frequencies[i] <= 30 and att is not None
                            ]
                            vhf_band = [
                                att
                                for i, att in enumerate(attenuations)
                                if 30 < frequencies[i] <= 300 and att is not None
                            ]
                            uhf_band = [
                                att
                                for i, att in enumerate(attenuations)
                                if 300 < frequencies[i] <= 3000 and att is not None
                            ]
                            shf_band = [
                                att for i, att in enumerate(attenuations) if frequencies[i] > 3000 and att is not None
                            ]

                            # Calculate average attenuation for each band
                            effectiveness["hf_band"] = sum(hf_band) / len(hf_band) if hf_band else 0
                            effectiveness["vhf_band"] = sum(vhf_band) / len(vhf_band) if vhf_band else 0
                            effectiveness["uhf_band"] = sum(uhf_band) / len(uhf_band) if uhf_band else 0
                            effectiveness["shf_band"] = sum(shf_band) / len(shf_band) if shf_band else 0

                        # Calculate min/max attenuation
                        valid_attens = [a for a in attenuations if a is not None]
                        if valid_attens:
                            max_atten = max(valid_attens)
                            max_atten_idx = attenuations.index(max_atten)
                            max_atten_freq = frequencies[max_atten_idx]

                            min_atten = min(valid_attens)
                            min_atten_idx = attenuations.index(min_atten)
                            min_atten_freq = frequencies[min_atten_idx]
                        else:
                            max_atten = 0
                            max_atten_freq = 0
                            min_atten = 0
                            min_atten_freq = 0

                        # Structure the spectrum data for the response
                        spectrum_data_dict = {
                            "frequencies": frequencies,
                            "baseline_levels": baseline_levels,
                            "hat_levels": hat_levels,
                            "attenuations": attenuations,
                            "effectiveness": effectiveness,
                            "max_attenuation": {"value": max_atten, "frequency": max_atten_freq},
                            "min_attenuation": {"value": min_atten, "frequency": min_atten_freq},
                            "test_state": test_state,
                        }
                except Exception as e:
                    print(f"Error processing spectrum data: {str(e)}")
                    traceback.print_exc()
                    spectrum_data_dict = {}
            else:
                # Check for an empty data marker from reset_test_state
                spectrum_data_dict = {
                    "frequencies": [],
                    "baseline_levels": [],
                    "hat_levels": [],
                    "attenuations": [],
                    "effectiveness": {"hf_band": 0.0, "vhf_band": 0.0, "uhf_band": 0.0, "shf_band": 0.0},
                    "max_attenuation": {"value": 0.0, "frequency": 0.0},
                    "min_attenuation": {"value": 0.0, "frequency": 0.0},
                    "test_state": "reset",
                }

                # Check if there's a reset event
                if latest_frequency_measurement and latest_frequency_measurement.get("event_type") in [
                    "test_reset",
                    "clear_all",
                ]:
                    print("Found reset event in latest_frequency_measurement, sending empty data")
                    # Ensure we send a test_state reset for polling requests too
                    spectrum_data_dict["test_state"] = "reset"
                    # Ready to set reset flags in the response later
                    reset_detected = True
                    reset_message = latest_frequency_measurement.get("message", "Test state has been reset")
                else:
                    reset_detected = False
                    reset_message = None

            # Build the response
            response_data = {
                "last_id": max_id,
                "leaderboard_classic": leaderboard_classic,
                "leaderboard_hybrid": leaderboard_hybrid,
            }

            # Add reset flags if needed
            if reset_detected:
                response_data["reset_detected"] = True
                response_data["reset_message"] = reset_message

            # Add new test data if available
            if new_test:
                response_data["new_test"] = new_test

            # Add spectrum data if available
            if spectrum_data_dict:
                response_data["spectrum_data"] = spectrum_data_dict

            # Return the JSON response
            return jsonify(response_data)

        except Exception as e:
            print(f"Error in billboard polling: {str(e)}")
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    # For SSE requests, set up a stream
    def generate():
        # Create a unique client ID
        client_id = id(time.time())

        # Create a queue for this client
        billboard_clients[client_id] = queue.Queue()

        try:
            # Send initial data
            initial_data = {"event_type": "connection_established", "timestamp": datetime.now()}

            yield f"data: {json.dumps(initial_data, cls=DateTimeEncoder)}\n\n"

            while True:
                try:
                    # Get data from the queue with timeout (to allow for keepalive)
                    data = billboard_clients[client_id].get(timeout=3.0)

                    # Convert to JSON and yield in SSE format
                    yield f"data: {json.dumps(data, cls=DateTimeEncoder)}\n\n"

                except queue.Empty:
                    # Send a keepalive comment every few seconds
                    yield ": keepalive\n\n"

                except Exception as e:
                    print(f"Error in billboard-updates stream: {str(e)}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Clean up when the client disconnects
            if client_id in billboard_clients:
                del billboard_clients[client_id]
                print(f"Billboard client {client_id} disconnected")

    # Return the response with SSE headers
    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"  # Disable proxy buffering
    return response


def format_datetime(dt_str):
    """
    Format a datetime string from the database to a more readable format.

    :param dt_str: Datetime string from database
    :type dt_str: str
    :return: Formatted datetime string
    :rtype: str
    """
    if not dt_str:
        return ""

    # If it's already a datetime object, just format it
    if isinstance(dt_str, datetime):
        return dt_str.strftime("%Y-%m-%d %H:%M:%S")

    # Handle string datetime formats
    try:
        # For SQLite default format (YYYY-MM-DD HH:MM:SS)
        if isinstance(dt_str, str) and " " in dt_str:
            # No need to replace space with T, parse directly
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        else:
            # Try to parse as ISO format
            dt = datetime.fromisoformat(str(dt_str))

        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        # If parsing fails, return the original string
        return str(dt_str)


@bp.route("/admin")
def admin():
    """
    Admin page for viewing and editing database information.

    :return: Rendered admin template
    :rtype: str
    """
    db = get_db()

    # Get all contestants
    contestants_rows = db.execute(
        "SELECT id, name, phone_number, email, notes, created FROM contestant ORDER BY name"
    ).fetchall()

    # Convert Row objects to dictionaries for JSON serialization
    contestants = []
    for row in contestants_rows:
        contestants.append(
            {
                "id": row["id"],
                "name": row["name"],
                "phone_number": row["phone_number"],
                "email": row["email"],
                "notes": row["notes"],
                "created": format_datetime(row["created"]),
            }
        )

    # Get all test results with contestant names
    test_results_rows = db.execute(
        """
        SELECT
            tr.id,
            tr.contestant_id,
            c.name as contestant_name,
            tr.test_date,
            tr.average_attenuation,
            tr.is_best_score,
            tr.hat_type
        FROM test_result tr
        JOIN contestant c ON tr.contestant_id = c.id
        ORDER BY tr.test_date DESC
        """
    ).fetchall()

    # Convert Row objects to dictionaries for JSON serialization
    test_results = []
    for row in test_results_rows:
        test_results.append(
            {
                "id": row["id"],
                "contestant_id": row["contestant_id"],
                "contestant_name": row["contestant_name"],
                "test_date": format_datetime(row["test_date"]),
                "average_attenuation": row["average_attenuation"],
                "is_best_score": row["is_best_score"],
                "hat_type": row["hat_type"] or "classic",
            }
        )

    return render_template("admin.html", contestants=contestants, test_results=test_results)


@bp.route("/admin/contestants", methods=["POST"])
def add_contestant_admin():
    """
    Add a new contestant from the admin page.

    :return: JSON response
    :rtype: Response
    """
    db = get_db()
    data = request.get_json()

    try:
        cursor = db.execute(
            """
            INSERT INTO contestant (name, phone_number, email, notes)
            VALUES (?, ?, ?, ?)
            """,
            (
                data.get("name", ""),
                data.get("phone_number", ""),
                data.get("email", ""),
                data.get("notes", ""),
            ),
        )
        db.commit()
        return jsonify({"success": True, "id": cursor.lastrowid})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/admin/contestants/<int:contestant_id>", methods=["PUT"])
def update_contestant_admin(contestant_id):
    """
    Update a contestant from the admin page.

    :param contestant_id: ID of the contestant to update
    :type contestant_id: int
    :return: JSON response
    :rtype: Response
    """
    db = get_db()
    data = request.get_json()

    try:
        db.execute(
            """
            UPDATE contestant
            SET name = ?, phone_number = ?, email = ?, notes = ?
            WHERE id = ?
            """,
            (
                data.get("name", ""),
                data.get("phone_number", ""),
                data.get("email", ""),
                data.get("notes", ""),
                contestant_id,
            ),
        )
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/admin/contestants/<int:contestant_id>", methods=["DELETE"])
def delete_contestant_admin(contestant_id):
    """
    Delete a contestant from the admin page.

    :param contestant_id: ID of the contestant to delete
    :type contestant_id: int
    :return: JSON response
    :rtype: Response
    """
    db = get_db()

    try:
        # First delete all test results for this contestant
        db.execute("DELETE FROM test_result WHERE contestant_id = ?", (contestant_id,))

        # Then delete the contestant
        db.execute("DELETE FROM contestant WHERE id = ?", (contestant_id,))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/admin/test-results", methods=["POST"])
def add_test_result_admin():
    """
    Add a new test result from the admin page.

    :return: JSON response
    :rtype: Response
    """
    db = get_db()
    data = request.get_json()

    try:
        # If setting this as best score, update existing best scores for this contestant
        if data.get("is_best_score"):
            db.execute(
                "UPDATE test_result SET is_best_score = 0 WHERE contestant_id = ?",
                (data.get("contestant_id"),),
            )

        cursor = db.execute(
            """
            INSERT INTO test_result (contestant_id, average_attenuation, is_best_score, hat_type)
            VALUES (?, ?, ?, ?)
            """,
            (
                data.get("contestant_id"),
                data.get("average_attenuation"),
                data.get("is_best_score", False),
                data.get("hat_type", "classic"),
            ),
        )
        db.commit()
        return jsonify({"success": True, "id": cursor.lastrowid})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/admin/test-results/<int:result_id>", methods=["PUT"])
def update_test_result_admin(result_id):
    """
    Update a test result from the admin page.

    :param result_id: ID of the test result to update
    :type result_id: int
    :return: JSON response
    :rtype: Response
    """
    db = get_db()
    data = request.get_json()

    try:
        # If setting this as best score, update existing best scores for this contestant
        if data.get("is_best_score"):
            db.execute(
                "UPDATE test_result SET is_best_score = 0 WHERE contestant_id = ?",
                (data.get("contestant_id"),),
            )

        db.execute(
            """
            UPDATE test_result
            SET contestant_id = ?, average_attenuation = ?, is_best_score = ?, hat_type = ?
            WHERE id = ?
            """,
            (
                data.get("contestant_id"),
                data.get("average_attenuation"),
                data.get("is_best_score", False),
                data.get("hat_type", "classic"),
                result_id,
            ),
        )
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/admin/test-results/<int:result_id>", methods=["DELETE"])
def delete_test_result_admin(result_id):
    """
    Delete a test result from the admin page.

    :param result_id: ID of the test result to delete
    :type result_id: int
    :return: JSON response
    :rtype: Response
    """
    db = get_db()

    try:
        # First delete any test data associated with this result
        db.execute("DELETE FROM test_data WHERE test_result_id = ?", (result_id,))

        # Then delete the test result itself
        db.execute("DELETE FROM test_result WHERE id = ?", (result_id,))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/test/cancel", methods=["POST"])
def cancel_test():
    """
    Cancel the current test and reset state.

    :return: JSON response with status
    :rtype: Response
    """
    try:
        # Reset all test state to ensure clean start for next test
        reset_test_state()

        return jsonify(
            {
                "status": "success",
                "message": "Test cancelled and state reset successfully.",
            }
        )
    except Exception as e:
        print(f"Error canceling test: {str(e)}")
        traceback.print_exc()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Error canceling test: {str(e)}",
                }
            ),
            500,
        )


def broadcast_test_event(event_data):
    """
    Broadcast an event to all connected clients.

    Args:
        event_data (dict): The event data to send.
    """
    # Send to frequency stream clients
    for client_queue in freq_clients.values():
        with contextlib.suppress(Exception):
            client_queue.put(event_data)

    # Send to billboard clients
    for client_queue in billboard_clients.values():
        with contextlib.suppress(Exception):
            client_queue.put(event_data)

    # Store the latest event for new clients


@bp.route("/test/reset", methods=["POST"])
def reset_test_state():
    """Reset the test state completely, clearing all measurement data.

    This function performs a full reset of the test environment:

    1. Clears all measurement data from the database
    2. Removes test-related data from the application config
    3. Notifies all connected clients to reset their displays
    4. Broadcasts empty spectrum data to force chart resets

    This should be called when starting a new test or abandoning an existing one.

    Returns:
        flask.Response: A JSON response indicating success or failure

    Notes:
        - This is the primary reset endpoint used by the application
        - For more aggressive resets, use force_reset_all_displays()
    """
    # Clear stored measurements from database
    try:
        db = get_db()
        db.execute("DELETE FROM measurement_cache")
        db.commit()
        print("Cleared all measurement cache data from database")
    except Exception as e:
        print(f"Error clearing measurement cache: {str(e)}")

    # Clear in-memory config data
    try:
        # Clear all measurement-related data from app config
        for key in ["BASELINE_DATA", "HAT_DATA", "ATTENUATION_DATA", "CURRENT_BASELINE"]:
            if key in current_app.config:
                del current_app.config[key]
        print("Cleared all measurement data from application config")
    except Exception as e:
        print(f"Error clearing config data: {str(e)}")

    # Reset the latest frequency measurement and broadcast to clients
    try:
        # Create a reset event to be sent to all clients
        reset_event = {
            "id": f"test_reset_{time.time()}",
            "event_type": "test_reset",
            "timestamp": datetime.now(),
            "message": "Test state has been reset",
            "force_client_reload": True,  # Add this flag to make clients reload completely
        }

        # Force a direct broadcast to ALL connected clients
        # First to frequency stream clients
        print(f"Broadcasting test_reset to {len(freq_clients)} frequency clients")
        sent_to_freq = 0
        for client_id, client_queue in freq_clients.items():
            try:
                client_queue.put(reset_event)
                sent_to_freq += 1
            except Exception as e:
                print(f"Failed to send reset to freq client {client_id}: {str(e)}")
        print(f"Successfully sent test_reset to {sent_to_freq} frequency clients")

        # Then to billboard clients
        print(f"Broadcasting test_reset to {len(billboard_clients)} billboard clients")
        sent_to_bb = 0
        for client_id, client_queue in billboard_clients.items():
            try:
                client_queue.put(reset_event)
                sent_to_bb += 1
            except Exception as e:
                print(f"Failed to send reset to billboard client {client_id}: {str(e)}")
        print(f"Successfully sent test_reset to {sent_to_bb} billboard clients")

        # Also store as latest measurement so new clients get it
        global latest_frequency_measurement
        latest_frequency_measurement = reset_event

        # Send additional billboard update with empty spectrum data to force chart reset
        billboard_update = {
            "event_type": "billboard_update",
            "timestamp": datetime.now(),
            "spectrum_data": {
                "frequencies": [],
                "baseline_levels": [],
                "hat_levels": [],
                "attenuations": [],
                "effectiveness": {"hf_band": 0.0, "vhf_band": 0.0, "uhf_band": 0.0, "shf_band": 0.0},
                "max_attenuation": {"value": 0.0, "frequency": 0.0},
                "min_attenuation": {"value": 0.0, "frequency": 0.0},
                "test_state": "reset",
                "progress": {"count": 0, "percent": 0},
            },
        }

        # Broadcast billboard update to all billboard clients
        print(f"Broadcasting billboard_update reset to {len(billboard_clients)} billboard clients")
        sent_bb_update = 0
        for client_id, client_queue in billboard_clients.items():
            try:
                client_queue.put(billboard_update)
                sent_bb_update += 1
            except Exception:
                print(f"Failed to send billboard_update to client {client_id}")
        print(f"Successfully sent billboard_update to {sent_bb_update} billboard clients")

        print("Reset frequency measurement data and notified all clients")
    except Exception as e:
        print(f"Error resetting frequency measurement: {str(e)}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Error resetting test state: {str(e)}"}), 500

    # Log the reset
    print("Test state has been fully reset - ready for new test")

    # Return success response
    return jsonify(
        {
            "status": "success",
            "message": "Test state has been fully reset",
            "details": {"freq_clients_notified": sent_to_freq, "billboard_clients_notified": sent_to_bb},
        }
    )


def force_reset_all_displays():
    """Force all connected clients to reset their displays immediately.

    This is a more aggressive reset operation that ensures all clients
    get the reset notification with an emergency flag that forces client-side
    emergency handling, causing a complete data flush and clear before
    any new data points are loaded.

    This function should be called at the start of baseline tests to ensure
    graphs are completely cleared of any previous data.

    Returns:
        int: The number of clients that successfully received the reset notification.

    Notes:
        - This function affects both frequency stream clients and billboard clients
        - The emergency flag causes client-side JavaScript to take immediate action
        - Existing message queues are preserved but reset messages are prioritized
    """
    global latest_frequency_measurement, freq_clients, freq_queues

    # Create an emergency reset event that all clients should prioritize
    emergency_reset = {
        "event_type": "test_reset",
        "emergency": True,  # Critical flag that clients will recognize
        "message": "EMERGENCY RESET - CLEAR ALL DISPLAYS IMMEDIATELY",
        "timestamp": datetime.now().isoformat(),
    }

    # Convert to SSE format for frequency stream clients
    freq_event = f"data: {json.dumps(emergency_reset)}\n\n"

    # Send to all frequency stream clients
    print(f"Sending emergency reset to {len(freq_clients)} clients")
    reset_sent_count = 0

    for client in list(freq_clients):
        try:
            # We add this to the beginning of each client's queue to ensure it's processed next
            client_queue = freq_queues[client]

            # Add to front of queue but preserve old queue contents after reset
            old_queue_contents = list(client_queue.queue)
            with client_queue.mutex:
                client_queue.queue.clear()
                client_queue.put_nowait(freq_event)  # Add reset event first

                # Put back the old contents (they'll be processed after reset)
                for item in old_queue_contents:
                    client_queue.put_nowait(item)

            reset_sent_count += 1
        except Exception as e:
            print(f"Error sending emergency reset to client: {e}")

    # Also force reset billboard clients
    for client_id in list(billboard_clients.keys()):
        billboard_clients[client_id]["reset_detected"] = True
        billboard_clients[client_id]["reset_message"] = "EMERGENCY RESET"

    # Update latest measurement to include emergency reset flag
    if latest_frequency_measurement:
        latest_frequency_measurement["emergency_reset"] = True

    print(f"Emergency reset sent to {reset_sent_count} clients successfully")
    return reset_sent_count
