# Tinfoil Hat Competition

A Flask web application for running and tracking the Tinfoil Hat Competition at Cypher Con in Milwaukee on April 9-10.

## Overview

The Tinfoil Hat Competition tests the signal attenuation properties of contestant-made tinfoil hats. The application:
- Manages contestant registration
- Controls HackRF One testing sequence
- Calculates attenuation scores
- Displays results on a leaderboard
- Visualizes test results in real-time

## Recent Updates

### Code Quality and Linting Improvements (March 2025)
- Updated code style configuration to use 120-character line length
- Fixed whitespace issues in SQL queries
- Improved exception handling using contextlib.suppress
- Modernized Ruff linting configuration
- Streamlined development workflow with targeted tox environments

### Real-time Measurement Functionality (March 2025)
- Added real-time frequency measurement endpoints
- Implemented a progress bar with current frequency display
- Visual feedback for measurement progress
- Interactive testing process with stop functionality
- Live chart updates as measurements are taken
- Enhanced frequency unit handling to ensure compatibility with HackRF

### Measurement and Error Handling Improvements
- Pure hardware measurements with no artificial simulation
- Fixed frequency unit conversion between MHz and Hz
- Added proper validation for HackRF's supported frequency range (1 MHz to 6 GHz)
- Enhanced error detection and recovery during measurements
- Better feedback for connection and measurement issues

## Requirements

- Python 3.8+ (primary development on Python 3.9)
- HackRF One with telescoping antenna
- Mannequin head for testing
- HackRF system tools

### Supported Python Versions
The application is tested primarily with Python 3.9. While the codebase should be compatible with Python 3.8 and 3.10+, these versions are not actively tested in the CI pipeline. If you encounter any issues with other Python versions, please report them.

## Hardware Setup

1. **Connect the HackRF One to your computer's USB port**

2. **Install HackRF Tools**

   - **MacOS**:
     ```
     brew install hackrf
     ```

   - **Ubuntu/Debian**:
     ```
     sudo apt-get install hackrf
     ```

   - **Windows**:
     Download and install from https://github.com/greatscottgadgets/hackrf/releases

3. **Verify HackRF connection**:
   ```
   hackrf_info
   ```
   
   The output should show your HackRF One device details.

## Software Setup

1. **Create and activate a virtual environment**:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install the package and dependencies**:
   ```
   pip install -e .
   ```

3. **Initialize the database**:
   ```
   python -m tinfoilhat.init_db
   ```

## Running the Application

Start the application with:
```
python run.py
```

Then open your browser and navigate to http://localhost:8000

## Usage Instructions

1. **Register Contestants**: Enter the contestant details in the registration form.

2. **Testing Process**:
   - Select a contestant from the dropdown menu
   - Click "Run Baseline Test" - watch as measurements happen in real-time
   - Place the tinfoil hat on the mannequin/test subject
   - Click "Measure Hat" - track the progress with the progress bar
   - Stop the measurement at any time if needed
   - Review the results and save them to the database
   - The application will calculate the RF attenuation and update the leaderboard

## Leaderboard

The leaderboard displays contestants ranked by the effectiveness of their tinfoil hats, measured by RF signal attenuation in dB.

## Hardware Recommendations

For optimal performance:
- Place the HackRF at a consistent distance from the test subject (about 30-50cm works well)
- Use an antenna suitable for the frequency ranges being tested
- Ensure a consistent testing environment with minimal RF interference
- Keep the HackRF in the same orientation throughout all tests
- Make sure the HackRF device has sufficient power (USB 3.0 port recommended)

## How It Works

### Testing Process

1. A contestant creates a tinfoil hat
2. Register the contestant in the application (or select from existing contestants)
3. Run a baseline test without the hat to measure ambient RF noise across all frequencies
4. Place the hat on the mannequin head and run the measurement test
5. View the results showing the average attenuation across all frequencies
6. If this is the contestant's best score, it will be highlighted and saved to the leaderboard

### Real Measurements

The application uses the HackRF One device to make real RF measurements:
1. For each frequency, the HackRF captures I/Q samples
2. The samples are processed to calculate power levels in dBm
3. Baseline and hat measurements are compared to calculate attenuation
4. Results are displayed in real-time as measurements progress
5. Statistics are calculated to show effectiveness across frequency bands

## Development

The project uses the following development tools:
- tox for testing and quality control
- black for code formatting
- ruff for linting
- isort for import sorting

### Code Style and Linting

This project follows modern Python coding standards with a 120-character line length limit. The configuration is set in `pyproject.toml`:

- **Black**: Formats code to a consistent style
- **isort**: Sorts and groups imports using Black-compatible settings
- **Ruff**: Performs fast, comprehensive linting with customized rules

We've configured the linters to work together without conflicts by:
1. Using the same line length (120) across all tools
2. Setting isort to use Black's profile
3. Moving Ruff's configuration to the modern `tool.ruff.lint` section format
4. Configuring Ruff to ignore certain warnings that would require substantial refactoring:
   - `BLE001` (blind exception catches)
   - `B904` (exception re-raising pattern)
   - `C901` (function complexity)

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run full test suite with linting and formatting
tox

# Run only the linting check
tox -e lint

# Run only the formatting check
tox -e format
```

### Project Structure

```
tinfoilhat/
├── __init__.py          - Package initialization
├── __main__.py          - Main entry point
├── app.py               - Flask app factory
├── db.py                - Database handling
├── routes.py            - HTTP endpoints and API
├── scanner.py           - HackRF One interface
├── schema.sql           - Database schema
└── templates/           - HTML templates
    └── index.html       - Main application page with real-time UI
```

## API Endpoints

- `/test/get_frequencies` - Get list of test frequencies (GET)
- `/test/measure_frequency` - Measure at a specific frequency (POST)
- `/test/save_results` - Save completed test results (POST)
- `/leaderboard` - Get current leaderboard data (GET)

## License

See LICENSE file for details. 