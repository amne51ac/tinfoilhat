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

### UI and Testing Workflow Improvements (March 2025)
- Redesigned testing flow to separate baseline and hat measurement phases
- Added a dedicated "Continue to Hat Measurement" modal with contestant selection
- Improved chart labels to show frequency and common radio band names (e.g., "89 (FM Radio)")
- Reduced spacing between UI elements for better visual cohesion
- Added ability to register new contestants directly from the measurement flow
- Renamed "Run Test" button to "Run Baseline Test" for clarity
- Fixed modal layering issues to ensure proper interaction with overlapping modals
- Consistent terminology throughout the application (standardized on "contestant")

### Spectrum Analyzer Enhancements (March 2025)
- Improved chart label formatting to show frequencies with human-readable band names
- Added tooltips showing detailed frequency information and descriptions
- Adjusted chart container height and padding for better display
- Enhanced layout of results display for better readability
- Added more visual feedback during the measurement process

### Server-Side Calculation Improvements (March 2025)
- Moved all attenuation and effectiveness calculations to server-side for consistency
- Eliminated discrepancies between client and server calculations
- Improved accuracy by only considering valid measurements in calculations
- Enhanced data validation logic on server for more reliable results
- Standardized frequency band processing across all calculations

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

1. **Register Contestants**: Use the "Add Contestant" button to enter participant details.

2. **Testing Process**:
   - Click "Run Baseline Test" to begin the testing process
   - The system will run a baseline test without the hat
   - When complete, you'll be prompted to place the hat on the mannequin/test subject
   - Select a contestant from the dropdown (or add a new one)
   - Choose the hat type (Classic or Hybrid)
   - The system will complete the test and automatically save the results
   - Review the results showing the average attenuation and effectiveness across frequency bands

3. **Viewing Results**:
   - Results appear automatically after test completion
   - Check the effectiveness across different frequency ranges
   - Note the frequencies where the hat performed best/worst
   - The leaderboard updates automatically if this is the contestant's best score

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
2. The operator runs a baseline test to measure ambient RF signals
3. The contestant places their hat on the mannequin head
4. The operator selects the contestant and hat type from the modal
5. The system measures RF signals with the hat in place
6. The application calculates attenuation by comparing baseline and hat measurements
7. Results show overall effectiveness and performance across different frequency bands
8. If this is the contestant's best score, it's saved to the leaderboard

### Hat Types

The system supports two types of hats:
- **Classic**: Made with tinfoil only
- **Hybrid**: Made with tinfoil plus other materials

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