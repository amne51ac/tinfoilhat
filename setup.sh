#!/bin/bash
# Setup script for the Tinfoil Hat Competition application

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