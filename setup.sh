#!/bin/bash
# Setup script for the Tinfoil Hat Competition application

# Check Python version
python_version=$(python3 --version)
if [[ ! $python_version =~ "Python 3.13" ]]; then
    echo "Error: Python 3.13 is required. Found: $python_version"
    echo "Please install Python 3.13 and try again."
    exit 1
fi

# Create a virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -e .

# Initialize the database
echo "Initializing database..."
python init_db.py

echo "Setup complete! You can now run the application with 'python run.py'" 