"""
Routes module for the Tinfoil Hat Competition application.

This module defines all HTTP endpoints for the Flask application.
"""

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    Response,
    stream_with_context,
)
import json
import time
from datetime import datetime

from tinfoilhat.db import get_db
from tinfoilhat.scanner import Scanner

bp = Blueprint("tinfoilhat", __name__, url_prefix="")

# Instead of creating the scanner at module level, create it for each request
# This will prevent issues when Flask reloads the application
scanner = None

# Global variable to track the latest frequency measurement
latest_frequency_measurement = None

# Add a custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
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
            if latest_frequency_measurement and latest_frequency_measurement.get('id') != last_measurement_id:
                # Update the last sent ID
                last_measurement_id = latest_frequency_measurement.get('id')
                
                # Send the measurement data
                yield f"data: {json.dumps(latest_frequency_measurement, cls=DateTimeEncoder)}\n\n"
            
            # Sleep to avoid high CPU usage
            time.sleep(0.1)
    
    # Set appropriate headers for SSE
    response = Response(stream_with_context(generate()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'  # Disable proxy buffering
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
    # Get baseline readings from HackRF
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
        baseline_data = scanner.get_baseline_readings()

        # Store in session for later use
        current_app.config["CURRENT_BASELINE"] = baseline_data

        # Return the data for visualization
        return jsonify(
            {
                "status": "success",
                "message": f"Baseline test completed with {scanner.samples_per_freq} samples per frequency.",
                "data": {
                    "frequencies": scanner.frequencies,
                    "baseline": baseline_data,
                    "samples_per_frequency": scanner.samples_per_freq,
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
        current_app.logger.error(f"Error in baseline test: {str(e)}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"An unexpected error occurred: {str(e)}",
                }
            ),
            500,
        )


@bp.route("/test/measure", methods=["POST"])
def measure_hat():
    """
    Measure a hat's attenuation after baseline has been established.

    All calculations are performed server-side for consistency:
    - Average attenuation is calculated using only valid measurements
    - Effectiveness values for each frequency band (HF, VHF, UHF, SHF) are calculated
    - Maximum and minimum attenuation frequencies are identified

    The client is only responsible for displaying these server-calculated values.

    :return: JSON response with test results
    :rtype: Response
    """
    # Get the baseline data from config
    baseline_data = current_app.config.get("CURRENT_BASELINE")
    if not baseline_data:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Baseline test has not been run. Please run baseline first.",
                }
            ),
            400,
        )

    # Get contestant ID from form
    contestant_id = request.form.get("contestant_id")
    if not contestant_id:
        return (
            jsonify({"status": "error", "message": "Contestant ID is required."}),
            400,
        )

    # Get hat measurements from HackRF
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
        hat_data = scanner.get_hat_readings()

        # Calculate attenuation
        attenuation_data = scanner.calculate_attenuation(baseline_data, hat_data)

        # All measurements from scanner are considered valid
        valid_measurements = [True] * len(attenuation_data)

        # Calculate average using only valid measurements
        total_attenuation = 0
        valid_count = 0
        for i, att in enumerate(attenuation_data):
            if valid_measurements[i]:
                total_attenuation += att
                valid_count += 1

        average_attenuation = float(total_attenuation / valid_count) if valid_count > 0 else 0.0
        print(f"DEBUG - Calculated average attenuation in measure_hat: {average_attenuation}")

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

        # Check if this is the best score for this contestant BEFORE inserting the new result
        best_score_result = db.execute(
            """
            SELECT MAX(average_attenuation) as best
            FROM test_result
            WHERE contestant_id = ?
            """,
            (contestant_id,),
        ).fetchone()

        # Check if the contestant has any previous entries
        has_previous_entries = best_score_result and best_score_result["best"] is not None

        # First score is always the best
        # Otherwise, compare with previous best - higher attenuation values are better
        # We want positive values (good shielding) to be considered better than negative values
        is_best = not has_previous_entries or (has_previous_entries and average_attenuation > best_score_result["best"])

        previous_best_score = best_score_result["best"] if has_previous_entries else None

        # Get hat type from request
        hat_type = request.form.get("hat_type", "classic")

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
            db.execute(
                """
                INSERT INTO test_data
                (test_result_id, frequency, baseline_level, hat_level, attenuation)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    test_result_id,
                    float(freq),
                    float(baseline_data[i]),
                    float(hat_data[i]),
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
                WHERE contestant_id = ? AND id != ?
                """,
                (contestant_id, test_result_id),
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
                score_message += " This is still your best score so far."
            else:
                score_message += f" Your previous best score of {previous_best_score:.2f} dB is better."
        else:
            if is_best:
                score_message = (
                    f"This is the best score for {contestant_name} "
                    f"with an attenuation of {average_attenuation:.2f} dB."
                )
            else:
                score_message = (
                    f"Not the best score for {contestant_name}. Previous best: "
                    f"{previous_best_score:.2f} dB, Current: {average_attenuation:.2f} dB."
                )

        # Convert frequencies to standard Python list to ensure JSON serialization
        frequencies_json = [float(f) for f in scanner.frequencies]
        baseline_json = [float(b) for b in baseline_data]
        hat_data_json = [float(h) for h in hat_data]
        attenuation_json = [float(a) for a in attenuation_data]

        # Return test results
        return jsonify(
            {
                "status": "success",
                "message": score_message,
                "data": {
                    "frequencies": frequencies_json,
                    "baseline": baseline_json,
                    "hat_measurements": hat_data_json,
                    "attenuation": attenuation_json,
                    "average_attenuation": average_attenuation,
                    "is_best_score": is_best,
                    "samples_per_frequency": scanner.samples_per_freq,
                    "contestant_name": contestant_name,
                    "effectiveness": effectiveness,
                    "max_attenuation": {
                        "value": max_attenuation,
                        "frequency": max_attenuation_freq,
                        "frequency_mhz": max_attenuation_freq / 1e6,
                    },
                    "min_attenuation": {
                        "value": min_attenuation,
                        "frequency": min_attenuation_freq,
                        "frequency_mhz": min_attenuation_freq / 1e6,
                    },
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
        current_app.logger.error(f"Error in hat measurement: {str(e)}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"An unexpected error occurred: {str(e)}",
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
        valid_measurements = []  # Track which measurements are valid
        missing_frequencies = []

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

        # Check if this is the best score for this contestant BEFORE inserting the new result
        best_score_result = db.execute(
            """
            SELECT MAX(average_attenuation) as best
            FROM test_result
            WHERE contestant_id = ?
            """,
            (contestant_id,),
        ).fetchone()

        # Check if the contestant has any previous entries
        has_previous_entries = best_score_result and best_score_result["best"] is not None

        # First score is always the best
        # Otherwise, compare with previous best - higher attenuation values are better
        # We want positive values (good shielding) to be considered better than negative values
        is_best = not has_previous_entries or (has_previous_entries and average_attenuation > best_score_result["best"])

        previous_best_score = best_score_result["best"] if has_previous_entries else None

        # Get hat type from request
        hat_type = request.json.get("hat_type", "classic")

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
                WHERE contestant_id = ? AND id != ?
                """,
                (contestant_id, test_result_id),
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
                score_message += " This is still your best score so far."
            else:
                score_message += f" Your previous best score of {previous_best_score:.2f} dB is better."
        else:
            if is_best:
                score_message = (
                    f"This is the best score for {contestant_name} "
                    f"with an attenuation of {average_attenuation:.2f} dB."
                )
            else:
                score_message = (
                    f"Not the best score for {contestant_name}. Previous best: "
                    f"{previous_best_score:.2f} dB, Current: {average_attenuation:.2f} dB."
                )

        # Clear stored data to prevent contaminating future tests
        clear_measurements()

        # After the test results are saved to the database, emit a test_complete event
        # with the same test_result_id from the saved test results
        try:
            db = get_db()
            contestant = db.execute("SELECT name, hat_type FROM contestant WHERE id = ?", (contestant_id,)).fetchone()
            
            # Retrieve the test result ID and data from the database
            test_result = db.execute(
                """
                SELECT id, date, average_attenuation 
                FROM test_result 
                WHERE contestant_id = ? 
                ORDER BY id DESC LIMIT 1
                """, 
                (contestant_id,)
            ).fetchone()
            
            if not test_result:
                raise Exception("Could not find the saved test result")
                
            test_result_id = test_result["id"]
            
            # Get the test data points for this test result
            test_data_points = db.execute(
                """
                SELECT frequency, baseline_level, hat_level, attenuation
                FROM test_data
                WHERE test_result_id = ?
                ORDER BY frequency
                """, 
                (test_result_id,)
            ).fetchall()
            
            # Extract frequencies and attenuations from the test data
            frequencies_mhz = [round(point["frequency"] / 1e6, 2) for point in test_data_points]
            attenuations = [point["attenuation"] for point in test_data_points]
            
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
                "attenuations": attenuations
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
                    "valid_frequencies": len(frequencies_mhz),
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
    recent_test = db.execute("""
        SELECT t.id as max_id, c.name, t.hat_type, ROUND(t.average_attenuation, 2) as attenuation, 
               t.test_date as date
        FROM test_result t
        JOIN contestant c ON t.contestant_id = c.id
        WHERE t.id = (SELECT MAX(id) FROM test_result)
    """).fetchone()
    
    # Get leaderboard data
    leaderboard_classic = get_leaderboard_data('classic')
    leaderboard_hybrid = get_leaderboard_data('hybrid')
    
    # Get spectrum data for the most recent test
    spectrum_data = {}
    if recent_test and recent_test["max_id"]:
        test_data_points = db.execute("""
            SELECT frequency, baseline_level, hat_level, attenuation
            FROM test_data
            WHERE test_result_id = ?
            ORDER BY frequency
        """, (recent_test["max_id"],)).fetchall()
        
        if test_data_points:
            frequencies = [round(point["frequency"] / 1e6, 2) for point in test_data_points]  # Convert to MHz
            baseline_levels = [point["baseline_level"] for point in test_data_points]
            hat_levels = [point["hat_level"] for point in test_data_points]
            attenuations = [point["attenuation"] for point in test_data_points]
            
            spectrum_data = {
                'frequencies': frequencies,
                'baseline_levels': baseline_levels,
                'hat_levels': hat_levels,
                'attenuations': attenuations
            }
    
    return render_template(
        "billboard.html",
        recent_test=recent_test,
        leaderboard_classic=leaderboard_classic,
        leaderboard_hybrid=leaderboard_hybrid,
        spectrum_data=spectrum_data
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
    results = db.execute("""
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
    """, (hat_type, hat_type)).fetchall()
    
    # Convert to list of dictionaries
    return [{'name': result["name"], 'attenuation': result["attenuation"]} for result in results]


@bp.route("/billboard-updates", methods=["GET"])
def billboard_updates():
    """Send SSE events when new test results are added."""
    last_id = request.args.get('last_id', type=int, default=0)
    
    # Check if this is an SSE request (EventSource connection) or regular HTTP request (polling)
    is_sse = request.headers.get('Accept') == 'text/event-stream'
    
    # For polling requests (non-SSE), just return the latest data as JSON
    if not is_sse:
        # Get the database connection
        db = get_db()
        
        # Get any new test results
        new_test = db.execute("""
            SELECT t.id as max_id, c.name, t.hat_type, ROUND(t.average_attenuation, 2) as attenuation, 
                   t.test_date as date
            FROM test_result t
            JOIN contestant c ON t.contestant_id = c.id
            WHERE t.id > ?
            ORDER BY t.id DESC
            LIMIT 1
        """, (last_id,)).fetchone()
        
        if not new_test or not new_test["max_id"]:
            # No new tests, return empty data
            return jsonify({
                'last_id': last_id,
                'new_test': None,
                'leaderboard_classic': [],
                'leaderboard_hybrid': [],
                'spectrum_data': {}
            })
        
        # Format date for display
        formatted_date = new_test["date"]
        
        # Get leaderboards data
        leaderboard_classic = get_leaderboard_data('classic')
        leaderboard_hybrid = get_leaderboard_data('hybrid')
        
        # Get spectrum data for the charts
        spectrum_data = {}
        test_data_points = db.execute("""
            SELECT frequency, baseline_level, hat_level, attenuation
            FROM test_data
            WHERE test_result_id = ?
            ORDER BY frequency
        """, (new_test["max_id"],)).fetchall()
        
        if test_data_points:
            frequencies = [round(point["frequency"] / 1e6, 2) for point in test_data_points]  # Convert to MHz
            baseline_levels = [point["baseline_level"] for point in test_data_points]
            hat_levels = [point["hat_level"] for point in test_data_points]
            attenuations = [point["attenuation"] for point in test_data_points]
            
            spectrum_data = {
                'frequencies': frequencies,
                'baseline_levels': baseline_levels,
                'hat_levels': hat_levels,
                'attenuations': attenuations
            }
        
        # Prepare data
        data = {
            'last_id': new_test["max_id"],
            'new_test': {
                'name': new_test["name"],
                'hat_type': new_test["hat_type"],
                'attenuation': new_test["attenuation"],
                'date': formatted_date
            },
            'leaderboard_classic': leaderboard_classic,
            'leaderboard_hybrid': leaderboard_hybrid,
            'spectrum_data': spectrum_data
        }
        
        return jsonify(data)
        
    # For SSE connections:
    def generate():
        nonlocal last_id
        app = current_app._get_current_object()  # Get the actual application object
        
        while True:
            # Create a new application context for each iteration
            with app.app_context():
                db = get_db()
                # Get any new test results
                new_test = db.execute("""
                    SELECT t.id as max_id, c.name, t.hat_type, ROUND(t.average_attenuation, 2) as attenuation, 
                           t.test_date as date
                    FROM test_result t
                    JOIN contestant c ON t.contestant_id = c.id
                    WHERE t.id > ?
                    ORDER BY t.id DESC
                    LIMIT 1
                """, (last_id,)).fetchone()
                
                if new_test and new_test["max_id"]:
                    # Format date for display
                    formatted_date = new_test["date"]
                    
                    # Get leaderboards data
                    leaderboard_classic = get_leaderboard_data('classic')
                    leaderboard_hybrid = get_leaderboard_data('hybrid')
                    
                    # Get spectrum data for the charts
                    spectrum_data = {}
                    test_data_points = db.execute("""
                        SELECT frequency, baseline_level, hat_level, attenuation
                        FROM test_data
                        WHERE test_result_id = ?
                        ORDER BY frequency
                    """, (new_test["max_id"],)).fetchall()
                    
                    if test_data_points:
                        frequencies = [round(point["frequency"] / 1e6, 2) for point in test_data_points]  # Convert to MHz
                        baseline_levels = [point["baseline_level"] for point in test_data_points]
                        hat_levels = [point["hat_level"] for point in test_data_points]
                        attenuations = [point["attenuation"] for point in test_data_points]
                        
                        spectrum_data = {
                            'frequencies': frequencies,
                            'baseline_levels': baseline_levels,
                            'hat_levels': hat_levels,
                            'attenuations': attenuations
                        }
                    
                    # Update last_id for the next iteration
                    last_id = new_test["max_id"]
                    
                    # Prepare data
                    data = {
                        'last_id': new_test["max_id"],
                        'new_test': {
                            'name': new_test["name"],
                            'hat_type': new_test["hat_type"],
                            'attenuation': new_test["attenuation"],
                            'date': formatted_date
                        },
                        'leaderboard_classic': leaderboard_classic,
                        'leaderboard_hybrid': leaderboard_hybrid,
                        'spectrum_data': spectrum_data
                    }
                    
                    # Convert to JSON and yield SSE format - use the DateTimeEncoder for datetime objects
                    yield f'data: {json.dumps(data, cls=DateTimeEncoder)}\n\n'
                    
            # Add a delay to avoid hammering the database
            time.sleep(1)
    
    # Set appropriate headers for SSE
    response = Response(stream_with_context(generate()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'  # Disable proxy buffering
    return response
