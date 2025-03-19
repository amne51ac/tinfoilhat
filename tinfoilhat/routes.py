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
)

from tinfoilhat.db import get_db
from tinfoilhat.scanner import Scanner

bp = Blueprint("tinfoilhat", __name__, url_prefix="")

# Instead of creating the scanner at module level, create it for each request
# This will prevent issues when Flask reloads the application
scanner = None

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
        "SELECT id FROM measurement_cache WHERE type = ? AND frequency = ?",
        (measurement_type, frequency_hz)
    ).fetchone()
    
    if existing:
        # Update existing measurement
        db.execute(
            "UPDATE measurement_cache SET power = ? WHERE id = ?",
            (power, existing['id'])
        )
    else:
        # Insert new measurement
        db.execute(
            "INSERT INTO measurement_cache (type, frequency, power) VALUES (?, ?, ?)",
            (measurement_type, frequency_hz, power)
        )
    
    db.commit()
    
    # Also store in app config for current request
    if measurement_type == 'baseline':
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
        "SELECT frequency, power FROM measurement_cache WHERE type = ?",
        (measurement_type,)
    ).fetchall()
    
    result = {}
    for row in measurements:
        result[str(int(row['frequency']))] = row['power']
    
    return result

def load_measurements_to_config():
    """
    Load measurements from database into application config.
    Call this at the start of relevant routes to ensure we have current data.
    """
    baseline_data = get_measurements('baseline')
    hat_data = get_measurements('hat')
    
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
            scanner = Scanner(samples_per_freq=1)  # Take only 1 sample per frequency for faster operation

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

    return render_template("index.html", leaderboard=leaderboard, contestants=contestants)


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
        leaderboard_data.append(
            {
                "rank": i + 1,
                "name": row["name"],
                "average_attenuation": row["average_attenuation"],
                "test_date": row["test_date"],
            }
        )

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
        (name, phone_number, email, notes),
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
        average_attenuation = float(sum(attenuation_data) / len(attenuation_data))

        # Calculate effectiveness in different frequency bands
        low_freq_indices = [i for i, f in enumerate(scanner.frequencies) if f < 1e9]  # Below 1 GHz
        mid_freq_indices = [i for i, f in enumerate(scanner.frequencies) if 1e9 <= f < 3e9]  # 1-3 GHz
        high_freq_indices = [i for i, f in enumerate(scanner.frequencies) if f >= 3e9]  # Above 3 GHz

        effectiveness = {
            "low_freq": (
                float(sum(attenuation_data[i] for i in low_freq_indices) / len(low_freq_indices))
                if low_freq_indices
                else 0.0
            ),
            "mid_freq": (
                float(sum(attenuation_data[i] for i in mid_freq_indices) / len(mid_freq_indices))
                if mid_freq_indices
                else 0.0
            ),
            "high_freq": (
                float(sum(attenuation_data[i] for i in high_freq_indices) / len(high_freq_indices))
                if high_freq_indices
                else 0.0
            ),
        }

        # Find peak attenuation and corresponding frequency
        max_attenuation_idx = attenuation_data.index(max(attenuation_data))
        max_attenuation = float(attenuation_data[max_attenuation_idx])
        max_attenuation_freq = float(scanner.frequencies[max_attenuation_idx])

        # Find minimum attenuation and corresponding frequency
        min_attenuation_idx = attenuation_data.index(min(attenuation_data))
        min_attenuation = float(attenuation_data[min_attenuation_idx])
        min_attenuation_freq = float(scanner.frequencies[min_attenuation_idx])

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
        
        # If this is their first test, it's automatically the best
        # Otherwise, compare with their previous best
        is_best = not has_previous_entries or (has_previous_entries and average_attenuation > best_score_result["best"])
        
        previous_best_score = best_score_result["best"] if has_previous_entries else None

        # Add test result
        cursor = db.execute(
            """
            INSERT INTO test_result (contestant_id, average_attenuation, is_best_score)
            VALUES (?, ?, ?)
            """,
            (contestant_id, average_attenuation, 1 if is_best else 0),
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

        # Convert frequencies to standard Python list to ensure JSON serialization
        frequencies_json = [float(f) for f in scanner.frequencies]
        baseline_json = [float(b) for b in baseline_data]
        hat_data_json = [float(h) for h in hat_data]
        attenuation_json = [float(a) for a in attenuation_data]

        # Return test results
        return jsonify(
            {
                "status": "success",
                "message": f"Hat measurement completed with {scanner.samples_per_freq} samples per frequency.",
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
            store_measurement('baseline', int(freq_hz), power)
        else:
            print(f"DEBUG - Stored hat for {freq_mhz} MHz: {power} dBm with key {str(int(freq_hz))}")
            store_measurement('hat', int(freq_hz), power)

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
            print(f"DEBUG - Calculated attenuation for {freq_mhz} MHz: {attenuation} dB (baseline: {baseline_power} dBm, hat: {power} dBm)")

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

    Required parameters:
    - contestant_id: ID of the contestant

    :return: JSON response with test results
    :rtype: Response
    """
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
                print(f"DEBUG - Found both: Baseline={baseline_data[str_freq]}, Hat={hat_data[str_freq]}")
            else:
                missing_frequencies.append(freq)
                # Use placeholder values if measurements are missing
                baseline_readings.append(-80.0)
                hat_readings.append(-80.0)
                print(f"DEBUG - Missing data: baseline_found={baseline_found}, hat_found={hat_found}")
                
        # Debug: Print constructed measurement arrays
        print("DEBUG - Baseline readings:", baseline_readings)
        print("DEBUG - Hat readings:", hat_readings)

        # Calculate attenuation
        attenuation_data = scanner.calculate_attenuation(baseline_readings, hat_readings)
        average_attenuation = float(sum(attenuation_data) / len(attenuation_data))

        # Calculate effectiveness in different frequency bands
        low_freq_indices = [i for i, f in enumerate(scanner.frequencies) if f < 1e9]  # Below 1 GHz
        mid_freq_indices = [i for i, f in enumerate(scanner.frequencies) if 1e9 <= f < 3e9]  # 1-3 GHz
        high_freq_indices = [i for i, f in enumerate(scanner.frequencies) if f >= 3e9]  # Above 3 GHz

        effectiveness = {
            "low_freq": (
                float(sum(attenuation_data[i] for i in low_freq_indices) / len(low_freq_indices))
                if low_freq_indices
                else 0.0
            ),
            "mid_freq": (
                float(sum(attenuation_data[i] for i in mid_freq_indices) / len(mid_freq_indices))
                if mid_freq_indices
                else 0.0
            ),
            "high_freq": (
                float(sum(attenuation_data[i] for i in high_freq_indices) / len(high_freq_indices))
                if high_freq_indices
                else 0.0
            ),
        }

        # Find peak and minimum attenuation
        max_attenuation_idx = attenuation_data.index(max(attenuation_data))
        max_attenuation = float(attenuation_data[max_attenuation_idx])
        max_attenuation_freq = float(scanner.frequencies[max_attenuation_idx])

        min_attenuation_idx = attenuation_data.index(min(attenuation_data))
        min_attenuation = float(attenuation_data[min_attenuation_idx])
        min_attenuation_freq = float(scanner.frequencies[min_attenuation_idx])

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
        
        # If this is their first test, it's automatically the best
        # Otherwise, compare with their previous best
        is_best = not has_previous_entries or (has_previous_entries and average_attenuation > best_score_result["best"])
        
        previous_best_score = best_score_result["best"] if has_previous_entries else None

        # Add test result
        cursor = db.execute(
            """
            INSERT INTO test_result (contestant_id, average_attenuation, is_best_score)
            VALUES (?, ?, ?)
            """,
            (contestant_id, average_attenuation, 1 if is_best else 0),
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

        # Clear stored data to prevent contaminating future tests
        clear_measurements()

        # Return test results
        return jsonify(
            {
                "status": "success",
                "message": f"Test results saved for contestant {contestant_name}",
                "data": {
                    "frequencies": [float(f) for f in scanner.frequencies],
                    "baseline": [float(b) for b in baseline_readings],
                    "hat_measurements": [float(h) for h in hat_readings],
                    "attenuation": [float(a) for a in attenuation_data],
                    "average_attenuation": average_attenuation,
                    "is_best_score": is_best,
                    "contestant_name": contestant_name,
                    "missing_frequencies": missing_frequencies,
                    "effectiveness": effectiveness,
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

    return jsonify({"status": "success", "data": {"frequencies": frequencies_hz}})
