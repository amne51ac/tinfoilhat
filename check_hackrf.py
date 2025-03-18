#!/usr/bin/env python
"""
HackRF Verification Tool

This script checks if HackRF tools are installed and the device is properly connected.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def check_command_exists(cmd):
    """Check if a command exists in the system path."""
    try:
        subprocess.run([cmd, "--help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        return False

def check_hackrf_connected():
    """Check if HackRF device is connected and recognized."""
    try:
        result = subprocess.run(["hackrf_info"], capture_output=True, text=True)
        if "HackRF One" in result.stdout:
            serial = None
            for line in result.stdout.splitlines():
                if "Serial number:" in line:
                    serial = line.split(":")[-1].strip()
            
            return True, serial
        else:
            return False, None
    except FileNotFoundError:
        return False, None
    except Exception as e:
        return False, str(e)

def test_frequency_sweep():
    """Test a quick frequency sweep to verify functionality."""
    try:
        print("Testing frequency sweep (will take 2 seconds)...")
        # Run a quick sweep from 100 MHz to 200 MHz
        cmd = [
            "hackrf_sweep",
            "-f", "100:200",  # 100-200 MHz
            "-N", "5",        # Only 5 samples
            "-a", "1"         # Average
        ]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(2)
        process.terminate()
        process.wait()
        
        if process.returncode is None or process.returncode == 0:
            return True
        else:
            stderr = process.stderr.read().decode()
            return False, stderr
    except Exception as e:
        return False, str(e)

def print_installation_instructions():
    """Print installation instructions based on OS."""
    print("\nHackRF Tools Installation Instructions:")
    
    if sys.platform.startswith('darwin'):  # macOS
        print("\nFor macOS (using Homebrew):")
        print("  brew install hackrf")
        
    elif sys.platform.startswith('linux'):  # Linux
        print("\nFor Debian/Ubuntu:")
        print("  sudo apt-get install hackrf")
        
    elif sys.platform.startswith('win'):  # Windows
        print("\nFor Windows:")
        print("  1. Download the latest release from https://github.com/greatscottgadgets/hackrf/releases")
        print("  2. Install the package following the instructions")
        
    print("\nAfter installation, you might need to install the USB rules/drivers for your OS.")
    print("See: https://github.com/greatscottgadgets/hackrf/wiki/Operating-System-Tips")

def main():
    """Main function to check HackRF setup."""
    print("=" * 60)
    print("HackRF Verification Tool")
    print("=" * 60)
    
    # Check if hackrf_info command exists
    if not check_command_exists("hackrf_info"):
        print("❌ HackRF tools not found. Please install HackRF tools.")
        print_installation_instructions()
        return 1
    
    print("✅ HackRF tools installed")
    
    # Check if HackRF is connected
    connected, serial = check_hackrf_connected()
    if not connected:
        print("❌ HackRF device not detected or not properly connected")
        print("   Please check USB connection and verify device is powered on")
        return 1
    
    print(f"✅ HackRF One detected (Serial: {serial})")
    
    # Test a quick frequency sweep
    sweep_ok = test_frequency_sweep()
    if sweep_ok is True:
        print("✅ Frequency sweep test successful")
    else:
        print(f"❌ Frequency sweep test failed: {sweep_ok[1]}")
        return 1
    
    print("\n" + "=" * 60)
    print("HackRF is properly set up and ready to use!")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 