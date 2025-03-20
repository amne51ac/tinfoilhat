"""
Scanner module for the Tinfoil Hat Competition application.

This module handles communication with the HackRF One device and processes
signal measurements.
"""

import os
import subprocess
import tempfile
import time

import numpy as np


class Scanner:
    """
    Scanner class to interface with the HackRF One device.

    This class manages signal measurements for the tinfoil hat competition
    by communicating directly with a HackRF One SDR device.
    """

    def __init__(
        self,
        num_frequencies: int = 50,
        min_freq: int = 2,
        max_freq: int = 5900,
        samples_per_freq: int = 1,
    ):
        """
        Initialize the scanner with frequency range.

        :param num_frequencies: Number of frequencies to test, defaults to 50
        :type num_frequencies: int, optional
        :param min_freq: Minimum frequency in MHz, defaults to 2 MHz
        :type min_freq: int, optional
        :param max_freq: Maximum frequency in MHz, defaults to 5900 MHz
        :type max_freq: int, optional
        :param samples_per_freq: Number of samples to take per frequency, defaults to 1
        :type samples_per_freq: int, optional
        """
        self.num_frequencies = num_frequencies
        self.min_freq = min_freq
        self.max_freq = max_freq
        self.samples_per_freq = samples_per_freq

        # Sample rate for HackRF (8 million samples per second)
        self.sample_rate = 8000000

        # Dictionary of common frequency bands with their names
        # Format: frequency in MHz -> (name, description)
        self.common_frequencies = {
            # AM/FM Radio
            88.5: ("FM Radio", "FM Radio Broadcasting"),
            98.1: ("FM Radio", "FM Radio Broadcasting"),
            107.9: ("FM Radio", "FM Radio Broadcasting"),
            # Cellular Bands
            850: ("Cellular", "GSM/CDMA 850 Band"),
            900: ("Cellular", "GSM/EGSM Band"),
            1800: ("Cellular", "DCS Band"),
            1900: ("Cellular", "PCS Band"),
            2100: ("Cellular", "UMTS/3G Band"),
            # LTE Bands
            700: ("LTE Band 12", "LTE 700 MHz"),
            1700: ("LTE Band 4", "AWS-1"),
            2600: ("LTE Band 7", "LTE 2600 MHz"),
            # 5G Bands
            3500: ("5G Mid-Band", "C-Band 5G"),
            4700: ("5G High-Band", "mmWave 5G"),
            # WiFi Bands
            2412: ("WiFi 2.4GHz", "Channel 1"),
            2437: ("WiFi 2.4GHz", "Channel 6"),
            2462: ("WiFi 2.4GHz", "Channel 11"),
            5180: ("WiFi 5GHz", "Channel 36"),
            5220: ("WiFi 5GHz", "Channel 44"),
            5320: ("WiFi 5GHz", "Channel 64"),
            5500: ("WiFi 5GHz", "Channel 100"),
            5700: ("WiFi 5GHz", "Channel 140"),
            # Bluetooth
            2402: ("Bluetooth", "Low Channels"),
            2441: ("Bluetooth", "Mid Channels"),
            2480: ("Bluetooth", "High Channels"),
            # GPS
            1575.42: ("GPS L1", "Civil GPS"),
            1227.60: ("GPS L2", "Military GPS"),
            # ISM Bands
            433: ("ISM 433MHz", "Remote Controls/Sensors"),
            915: ("ISM 915MHz", "ISM Band"),
            2450: ("ISM 2.4GHz", "ISM Band"),
            5800: ("ISM 5.8GHz", "ISM Band"),
            # TV Broadcasting
            174: ("VHF TV", "Television Broadcasting"),
            470: ("UHF TV", "Television Broadcasting"),
            # Amateur Radio
            144: ("2m Amateur", "Ham Radio"),
            432: ("70cm Amateur", "Ham Radio"),
            1296: ("23cm Amateur", "Ham Radio"),
            # Satellites
            137: ("NOAA Weather", "Weather Satellites"),
            1090: ("ADS-B", "Aircraft Tracking"),
            # Wireless Microphones
            518: ("Wireless Mic", "UHF Wireless Mics"),
            # RFID
            865: ("RFID UHF", "UHF RFID"),
            2455: ("RFID", "Microwave RFID"),
            # Medical Devices
            2400: ("Medical", "Medical Telemetry"),
            # Smart Home
            868: ("Smart Home", "Z-Wave"),
            908: ("Smart Home", "ZigBee"),
        }

        # Determine how many common frequencies to include (50-85% of total)
        common_freq_count = int(self.num_frequencies * 0.7)  # 70% common frequencies
        remaining_freq_count = self.num_frequencies - common_freq_count

        # Filter common frequencies to be within our min-max range
        filtered_common = {f: v for f, v in self.common_frequencies.items() if self.min_freq <= f <= self.max_freq}

        # If we have more common frequencies than needed, select a subset
        self.selected_frequencies = []
        self.frequency_labels = {}

        if len(filtered_common) > common_freq_count:
            # Take a well-distributed subset of common frequencies
            freq_keys = sorted(list(filtered_common.keys()))
            step = len(freq_keys) / common_freq_count
            indices = [int(i * step) for i in range(common_freq_count)]

            for idx in indices:
                if idx < len(freq_keys):
                    freq = freq_keys[idx]
                    self.selected_frequencies.append(freq)
                    self.frequency_labels[freq] = filtered_common[freq]
        else:
            # Use all common frequencies and adjust remaining_freq_count
            self.selected_frequencies = list(filtered_common.keys())
            self.frequency_labels = filtered_common
            remaining_freq_count = self.num_frequencies - len(self.selected_frequencies)

        # If we have any remaining slots, add evenly spaced frequencies
        if remaining_freq_count > 0:
            # Calculate evenly spaced frequencies for remaining slots
            step = (self.max_freq - self.min_freq) / (remaining_freq_count + 1)
            for i in range(1, remaining_freq_count + 1):
                new_freq = self.min_freq + i * step
                # Avoid duplicates and frequencies very close to existing ones
                is_duplicate = False
                for existing_freq in self.selected_frequencies:
                    if abs(existing_freq - new_freq) < 5:  # within 5 MHz
                        is_duplicate = True
                        break

                if not is_duplicate:
                    self.selected_frequencies.append(new_freq)

        # Sort frequencies for proper display
        self.frequencies = sorted(self.selected_frequencies)

        # Log the frequency points we'll test
        print(f"Will test the following frequencies (MHz): {self.frequencies}")
        print(f"Frequency labels: {self.frequency_labels}")

        # Verify HackRF presence
        self.hackrf_available = self._check_hackrf()
        if not self.hackrf_available:
            print("⚠️  HackRF One not detected or not connected properly.")
            print("Please ensure HackRF tools are installed and device is connected.")
            print("You can run python check_hackrf.py for detailed diagnostics.")
            # Don't exit - this allows the application to initialize without a HackRF
            # and possibly recover later if the device becomes available

        # Create a temp directory for our files
        self.temp_dir = tempfile.mkdtemp(prefix="hackrf_")
        print(f"Using temporary directory: {self.temp_dir}")

    def __del__(self):
        """Clean up temporary directory when object is destroyed"""
        try:
            if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
                import shutil

                shutil.rmtree(self.temp_dir)
                print(f"Removed temporary directory: {self.temp_dir}")
        except Exception as e:
            print(f"Error cleaning up: {str(e)}")

    def _check_hackrf(self) -> bool:
        """
        Check if HackRF device is connected and available.

        :return: True if HackRF is available, False otherwise
        :rtype: bool
        """
        # Allow up to 3 retries for detecting the HackRF
        for attempt in range(1, 4):
            try:
                # Run hackrf_info command to check device
                result = subprocess.run(["hackrf_info"], capture_output=True, text=True, timeout=5)

                if "HackRF One" in result.stdout:
                    print("HackRF One detected successfully")

                    # Extract serial number
                    serial = None
                    for line in result.stdout.splitlines():
                        if "Serial number:" in line:
                            serial = line.split(":")[-1].strip()
                            print(f"Using HackRF with serial: {serial}")

                    return True
                else:
                    print(f"WARNING: HackRF One not detected on attempt {attempt}/3. Retrying...")
                    if attempt < 3:
                        time.sleep(1)  # Wait before retrying
                    else:
                        print(
                            "WARNING: HackRF One not detected after multiple attempts. "
                            "Make sure the device is connected."
                        )
                        return False
            except FileNotFoundError:
                print("ERROR: hackrf_info command not found. Please ensure HackRF tools are installed.")
                print("Install instructions: https://github.com/greatscottgadgets/hackrf/wiki/Operating-System-Tips")
                return False
            except subprocess.TimeoutExpired:
                print(f"ERROR: hackrf_info command timed out on attempt {attempt}/3.")
                if attempt < 3:
                    print("   Retrying after timeout...")
                    time.sleep(1)  # Wait before retrying
                else:
                    print("ERROR: hackrf_info command timed out after multiple attempts.")
                    print("The device might be busy or unresponsive.")
                    print("Try disconnecting and reconnecting the HackRF device.")
                    return False
            except Exception as e:
                print(f"ERROR checking HackRF on attempt {attempt}/3: {str(e)}")
                if attempt < 3:
                    time.sleep(1)  # Wait before retrying
                else:
                    print(f"ERROR checking HackRF after multiple attempts: {str(e)}")
                    return False

        return False  # Should not reach here but just in case

    def refresh_hackrf(self) -> bool:
        """
        Refresh the HackRF connection.
        This can be called if operations fail to attempt to recover the device.

        :return: True if HackRF is available after refresh, False otherwise
        :rtype: bool
        """
        print("Refreshing HackRF connection...")
        self.hackrf_available = self._check_hackrf()
        return self.hackrf_available

    def _analyze_iq_samples(self, samples: bytes) -> float:
        """
        Analyze IQ samples to determine power level.

        :param samples: Raw IQ samples from HackRF as bytes
        :type samples: bytes
        :return: Power level in dBm
        :rtype: float
        """
        # Check if we have enough samples
        if len(samples) < 8:  # Need at least a few I/Q pairs
            print("Warning: Not enough samples for analysis")
            return -80  # Return a reasonable fallback value

        # Convert bytes to 8-bit signed integers
        iq_data = np.frombuffer(samples, dtype=np.int8)

        # Separate I and Q components
        i_data = iq_data[::2]
        q_data = iq_data[1::2]

        # Normalize values (convert from 8-bit int to float in range [-1, 1])
        i_norm = i_data / 127.0  # 127 is max value for int8
        q_norm = q_data / 127.0

        # Create complex numbers
        complex_samples = i_norm + 1j * q_norm

        # Calculate power: mean of magnitude squared
        # This gives us power in linear scale
        power_linear = np.mean(np.abs(complex_samples) ** 2)

        # Convert to dBm
        # P(dBm) = 10 * log10(P_linear) + correction_factor
        # The correction factor depends on HackRF calibration, gain settings, etc.

        # Apply appropriate correction factor based on HackRF characteristics
        # This will need to be tuned based on your specific device and setup
        correction_factor = -50  # Empirical correction factor in dB

        # Calculate power in dBm
        power_dbm = 10 * np.log10(power_linear + 1e-10) + correction_factor

        # Round to 2 decimal places
        power_dbm = round(power_dbm, 2)

        return power_dbm

    def _measure_power_at_frequency(self, freq_hz: float) -> float:
        """
        Measure power at a specific frequency.

        :param freq_hz: Frequency in Hz
        :type freq_hz: float
        :return: Power level in dBm
        :rtype: float
        """
        # Make sure HackRF is available
        if not self.hackrf_available:
            print("HackRF not available during measurement. Attempting to refresh connection...")
            if not self.refresh_hackrf():
                raise RuntimeError(
                    f"HackRF device is not available and reconnection failed. Cannot measure at {freq_hz / 1e6} MHz."
                )

        # Ensure freq_hz is within valid range for HackRF (1 MHz to 6 GHz)
        if freq_hz < 1e6 or freq_hz > 6e9:
            raise RuntimeError(f"Frequency {freq_hz / 1e6} MHz is outside the supported range (1 MHz to 6 GHz)")

        # Convert to MHz for display/debugging purposes only
        freq_mhz = freq_hz / 1e6

        # Set appropriate gain based on frequency range
        # Lower frequencies often need less gain to avoid overloading
        if freq_mhz < 100:
            lna_gain = 8
            vga_gain = 12
        elif freq_mhz < 500:
            lna_gain = 16
            vga_gain = 16
        elif freq_mhz < 1500:
            lna_gain = 24
            vga_gain = 20
        elif freq_mhz < 3000:
            lna_gain = 32
            vga_gain = 24
        elif freq_mhz < 4500:
            lna_gain = 40
            vga_gain = 26
        else:  # 4500 - 5900 MHz
            lna_gain = 40
            vga_gain = 30

        # Number of samples to capture
        num_samples = 262144  # 2^18, a reasonable size for analysis

        # Create a unique filename in our temp directory
        timestamp = int(time.time())
        output_file = os.path.join(self.temp_dir, f"power_meas_{timestamp}_{int(freq_mhz)}.bin")

        # Build the hackrf_transfer command
        # -r: receive mode, save to file
        # -f: frequency in Hz
        # -l: LNA gain (0-40 dB in 8 dB steps)
        # -g: VGA gain (0-62 dB in 2 dB steps)
        # -a: enable amp (1) or disable (0)
        # -n: number of samples to transfer
        cmd = [
            "hackrf_transfer",
            "-r",
            output_file,
            "-f",
            str(int(freq_hz)),  # HackRF expects integer Hz
            "-l",
            str(lna_gain),
            "-g",
            str(vga_gain),
            "-a",
            "1",  # Enable amp
            "-n",
            str(num_samples),
        ]

        try:
            # Run the command with a timeout
            print(f"Measuring at {freq_mhz} MHz with LNA gain {lna_gain} dB, VGA gain {vga_gain} dB")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)  # Increased timeout

            if result.returncode != 0:
                error_msg = f"Error measuring frequency {freq_mhz} MHz: return code {result.returncode}"
                if result.stderr:
                    error_msg += f"\nError output: {result.stderr}"
                print(error_msg)
                raise RuntimeError(error_msg)

            # Check if the output file exists and has data
            if not os.path.exists(output_file):
                error_msg = f"No output file created for frequency {freq_mhz} MHz"
                print(error_msg)
                raise RuntimeError(error_msg)

            if os.path.getsize(output_file) == 0:
                error_msg = f"No data captured for frequency {freq_mhz} MHz (empty file)"
                print(error_msg)
                raise RuntimeError(error_msg)

            # Read the IQ samples from the file
            with open(output_file, "rb") as f:
                samples = f.read()

            # Remove the temporary file
            try:
                os.remove(output_file)
            except Exception as e:
                print(f"Warning: Failed to remove temporary file {output_file}: {str(e)}")

            # Analyze the samples
            power = self._analyze_iq_samples(samples)

            # Apply frequency-dependent adjustment
            # Higher frequencies generally have higher path loss
            freq_adjustment = -0.01 * (freq_mhz / 10)  # -0.1 dB per 100 MHz
            power += freq_adjustment

            print(f"Measured power at {freq_mhz} MHz: {power:.2f} dBm")
            return power

        except subprocess.TimeoutExpired:
            error_msg = f"Timeout measuring frequency {freq_mhz} MHz"
            print(error_msg)
            # Check if HackRF is still available after timeout
            if not self.refresh_hackrf():
                raise RuntimeError(f"HackRF connection lost during timeout at {freq_mhz} MHz")
            # Apply frequency-dependent default power for timeout
            freq_factor = min(1.0, freq_mhz / 2000.0)
            default_power = -75 - (freq_factor * 10)
            return round(default_power, 2)

        except Exception as e:
            error_msg = f"Error measuring frequency {freq_mhz} MHz: {str(e)}"
            print(error_msg)
            # Check if this is a HackRF-related error and we should try to reconnect
            if "hackrf" in str(e).lower() or "usb" in str(e).lower():
                print("Possible HackRF connection issue. Attempting to refresh...")
                if not self.refresh_hackrf():
                    raise RuntimeError(f"HackRF connection lost during measurement at {freq_mhz} MHz: " f"{str(e)}")
            raise

    def get_baseline_readings(self) -> list[float]:
        """
        Measure baseline power at all frequencies.

        :return: List of power readings in dBm at each frequency
        :rtype: List[float]
        """
        if not self.hackrf_available:
            print("HackRF not available. Attempting to refresh connection...")
            if not self.refresh_hackrf():
                raise RuntimeError(
                    "HackRF device is not available and reconnection failed. " "Cannot perform measurements."
                )

        print("Starting baseline measurements...")

        baseline = []
        for freq in self.frequencies:
            # Take multiple measurements and average them for more stability
            readings = []
            for i in range(self.samples_per_freq):
                try:
                    reading = self._measure_power_at_frequency(freq * 1e6)
                    readings.append(reading)
                    time.sleep(0.5)  # Short delay between measurements
                except Exception as e:
                    print(f"Error measuring at {freq} MHz (sample {i + 1}/{self.samples_per_freq}): " f"{str(e)}")
                    # Try to refresh HackRF connection if we encounter an error
                    if "hackrf" in str(e).lower() or "usb" in str(e).lower():
                        print("Possible HackRF connection issue detected. " "Attempting to refresh...")
                        if self.refresh_hackrf():
                            print("HackRF connection restored. Retrying measurement...")
                        else:
                            print("Failed to restore HackRF connection.")
                            raise RuntimeError(f"HackRF connection lost during measurement: {str(e)}")

            if not readings:
                raise RuntimeError(f"Failed to take any measurements at {freq} MHz")

            # Average the readings
            avg_power = sum(readings) / len(readings)
            print(f"Average baseline at {freq} MHz: {avg_power:.2f} dBm")
            baseline.append(avg_power)

        print("Baseline measurements completed")
        print(f"Baseline readings: {baseline}")
        return baseline

    def get_hat_readings(self) -> list[float]:
        """
        Measure power with a hat in place.

        :return: List of power readings in dBm at each frequency
        :rtype: List[float]
        """
        if not self.hackrf_available:
            print("HackRF not available. Attempting to refresh connection...")
            if not self.refresh_hackrf():
                raise RuntimeError(
                    "HackRF device is not available and reconnection failed. " "Cannot perform measurements."
                )

        print("\n========= PLACE TINFOIL HAT ON MANNEQUIN NOW =========")
        print("Starting hat measurements...")

        hat_readings = []
        for freq in self.frequencies:
            # Take multiple measurements and average them for more stability
            readings = []
            for i in range(self.samples_per_freq):
                try:
                    reading = self._measure_power_at_frequency(freq * 1e6)
                    # For testing: Uncomment to add artificial attenuation if testing
                    # without a real hat
                    # reading -= 5 + freq % 10  # artificial attenuation that varies with frequency
                    readings.append(reading)
                    time.sleep(0.5)  # Short delay between measurements
                except Exception as e:
                    print(f"Error measuring at {freq} MHz (sample {i + 1}/{self.samples_per_freq}): " f"{str(e)}")
                    # Try to refresh HackRF connection if we encounter an error
                    if "hackrf" in str(e).lower() or "usb" in str(e).lower():
                        print("Possible HackRF connection issue detected. " "Attempting to refresh...")
                        if self.refresh_hackrf():
                            print("HackRF connection restored. Retrying measurement...")
                        else:
                            print("Failed to restore HackRF connection.")
                            raise RuntimeError(f"HackRF connection lost during measurement: {str(e)}")

            if not readings:
                raise RuntimeError(f"Failed to take any measurements at {freq} MHz")

            # Average the readings
            avg_power = sum(readings) / len(readings)
            print(f"Average hat reading at {freq} MHz: {avg_power:.2f} dBm")
            hat_readings.append(avg_power)

        print("Hat measurements completed")
        print(f"Hat readings: {hat_readings}")
        return hat_readings

    def calculate_attenuation(self, baseline: list[float], hat_readings: list[float]) -> list[float]:
        """
        Calculate attenuation at each frequency by comparing baseline to hat readings.

        :param baseline: Baseline readings without hat
        :type baseline: List[float]
        :param hat_readings: Readings with hat
        :type hat_readings: List[float]
        :return: Attenuation values at each frequency
        :rtype: List[float]
        """
        print("\n========= CALCULATING ATTENUATION =========")

        # Attenuation is the difference between baseline and hat readings
        # A positive value means the hat reduced the signal (good)
        attenuation = []

        # Check for valid readings
        if len(baseline) != len(hat_readings) or len(baseline) == 0:
            print("ERROR: Invalid readings data. Cannot calculate attenuation.")
            return [0.1] * len(self.frequencies)

        for freq, base, hat in zip(self.frequencies, baseline, hat_readings, strict=False):
            # Lower hat reading means better attenuation (more negative dBm)
            # So we subtract hat from baseline to get positive attenuation values

            # Calculate raw attenuation
            att = base - hat

            # Handle potential measurement errors
            if att < 0:
                # Negative attenuation means the signal got stronger with the hat
                # This could be due to reflection, resonance, or other RF effects
                print(
                    f"Note: Negative attenuation detected at {freq} MHz: {att:.2f} dB. Signal is stronger with the hat."
                )
                # We'll keep the negative value for accurate representation

            # Apply frequency-dependent adjustment
            # (tinfoil hats typically perform better at higher frequencies)
            # Calculate frequency factor (normalized to 0-1 range)
            freq_factor = (
                (freq - self.min_freq) / (self.max_freq - self.min_freq) if self.max_freq > self.min_freq else 0
            )

            # Very slight boost to attenuation at higher frequencies (at most 1dB)
            if freq_factor > 0.5:
                att += freq_factor * 0.5

            # Round to one decimal place for cleaner display
            att = round(att, 1)

            print(f"At {freq} MHz: Baseline {base:.2f} dBm, Hat {hat:.2f} dBm, " f"Attenuation {att:.1f} dB")
            attenuation.append(att)

        print("\n========= ATTENUATION SUMMARY =========")
        print(f"Frequencies (MHz): {self.frequencies}")
        print(f"Attenuation (dB): {[round(a, 1) for a in attenuation]}")

        # Check if hat is effective
        if max(attenuation) < 2.0 and all(a >= 0 for a in attenuation):
            print("\nWARNING: The hat shows minimal attenuation (<2dB) - " "this might not be an effective RF shield.")
        elif any(a < 0 for a in attenuation):
            neg_freqs = [self.frequencies[i] for i, a in enumerate(attenuation) if a < 0]
            print(f"\nWARNING: The hat shows negative attenuation at frequencies: {neg_freqs} MHz.")
            print("This means the signal is stronger with the hat than without it at these frequencies.")
        else:
            peak_attenuation = max(attenuation)
            peak_freq = self.frequencies[attenuation.index(peak_attenuation)]
            print(f"\nThe hat performs best at {peak_freq} MHz with " f"{peak_attenuation:.1f} dB attenuation")

        return attenuation
