# Tinfoil Hat Competition

A Flask web application for running and tracking the Tinfoil Hat Competition at Cypher Con in Milwaukee on April 9-10.

## Overview

The Tinfoil Hat Competition tests the signal attenuation properties of contestant-made tinfoil hats. The application:
- Manages contestant registration
- Controls HackRF One testing sequence
- Calculates attenuation scores
- Displays results on a leaderboard
- Visualizes test results in real-time

## Requirements

- Python 3.8+
- HackRF One with telescoping antenna (for real measurements, simulated in development mode)
- Mannequin head for testing
- HackRF system tools

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
   - First, measure the baseline (without the hat)
   - Place the tinfoil hat on the mannequin/test subject
   - Run the measurement test
   - The application will calculate the RF attenuation and update the leaderboard

## Leaderboard

The leaderboard displays contestants ranked by the effectiveness of their tinfoil hats, measured by RF signal attenuation in dB.

## Hardware Recommendations

For optimal performance:
- Place the HackRF at a consistent distance from the test subject
- Use an antenna suitable for the frequency ranges being tested
- Ensure a consistent testing environment with minimal RF interference
- Keep the HackRF in the same orientation throughout all tests

## How It Works

### Testing Process

1. A contestant creates a tinfoil hat
2. Register the contestant in the application (or select from existing contestants)
3. Run a baseline test without the hat to measure ambient RF noise
4. Place the hat on the mannequin head and run the measurement test
5. View the results showing the average attenuation across all frequencies
6. If this is the contestant's best score, it will be highlighted and saved to the leaderboard

### Development Mode

In development mode, the application simulates the HackRF One measurements with random values. In production, you would replace the simulated scanner with actual HackRF One measurements.

## Development

The project uses the following development tools:
- tox for testing and quality control
- black for code formatting
- ruff for linting
- isort for import sorting

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run full test suite with linting and formatting
tox
```

### Project Structure

```
tinfoilhat/
├── __init__.py          - Package initialization
├── __main__.py          - Main entry point
├── app.py               - Flask app factory
├── db.py                - Database handling
├── routes.py            - HTTP endpoints
├── scanner.py           - HackRF One interface
├── schema.sql           - Database schema
└── templates/           - HTML templates
    └── index.html       - Main application page
```

## License

See LICENSE file for details. 