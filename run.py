#!/usr/bin/env python
"""
Run script for the Tinfoil Hat Competition application.

This script checks for HackRF availability and then starts the Flask application.
"""

import os
import sys
import subprocess
import time

def check_hackrf_available():
    """Check if HackRF tools are installed and device is connected."""
    MAX_RETRIES = 3
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Checking for HackRF device (attempt {attempt}/{MAX_RETRIES})...")
            
            # Check if hackrf_info command exists
            result = subprocess.run(['hackrf_info'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode == 0 and "HackRF One" in result.stdout:
                print("✅ HackRF One detected!")
                
                # Extract serial number for confirmation
                serial = None
                for line in result.stdout.splitlines():
                    if "Serial number:" in line:
                        serial = line.split(":")[-1].strip()
                
                if serial:
                    print(f"   Serial number: {serial}")
                    
                return True
            else:
                print("⚠️  HackRF One not detected on attempt", attempt)
                if attempt < MAX_RETRIES:
                    print("   Waiting 2 seconds before retrying...")
                    time.sleep(2)
                else:
                    print("⚠️  HackRF One not detected or not connected properly.")
                    print("Please ensure HackRF tools are installed and device is connected.")
                    print("You can run python check_hackrf.py for detailed diagnostics.")
                    
                    if result.stderr:
                        print("\nError output:")
                        print(result.stderr)
                    
                    user_input = input("Continue without HackRF? The application will not function correctly. (y/n): ")
                    return user_input.lower() == 'y'
                
        except FileNotFoundError:
            print("⚠️  HackRF tools not found in your system PATH.")
            print("Please install HackRF tools following the instructions in README.md")
            print("You can run python check_hackrf.py for detailed diagnostics.")
            
            user_input = input("Continue without HackRF? The application will not function correctly. (y/n): ")
            return user_input.lower() == 'y'

def get_available_port():
    """Find an available port, defaulting to 8000."""
    port = 8000
    return port

def main():
    """Main function to run the app."""
    # Check for HackRF
    if not check_hackrf_available():
        print("Exiting application due to HackRF unavailability.")
        return 1
    
    # Import the Flask app
    from tinfoilhat.app import create_app
    app = create_app()
    
    # Determine port (defaults to 8000 to avoid conflicting with common ports)
    port = get_available_port()
    
    print(f"\nStarting Tinfoil Hat Competition application on http://127.0.0.1:{port}")
    print("Press CTRL+C to quit\n")
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=port, debug=True)
    
    return 0

if __name__ == '__main__':
    sys.exit(main()) 