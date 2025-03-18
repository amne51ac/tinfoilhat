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

## Quick Start

### Using Setup Scripts

On Linux/macOS:
```bash
./setup.sh
python run.py
```

On Windows:
```
setup.bat
python run.py
```

### Manual Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install the package:
   ```bash
   pip install -e .
   ```

3. Initialize the database:
   ```bash
   python init_db.py
   ```

4. Run the application:
   ```bash
   python run.py
   ```

5. Open your browser and navigate to http://localhost:8000

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