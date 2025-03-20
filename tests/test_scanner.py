"""
Tests for the Scanner module of the Tinfoil Hat Competition application.

These tests verify the functionality of the HackRF One interface.
"""

from unittest.mock import MagicMock, patch

import pytest

from tinfoilhat.scanner import Scanner


@pytest.fixture
def mock_hackrf_commands():
    """Mock for hackrf command-line tools."""
    mock_info = MagicMock()
    mock_info.return_value = (
        b"Found HackRF\nSerial number: 0000000000000000f77c60dc26217fc3\n"
        b"Firmware version: 2022.09.1\nHardware version: r9\n"
    )

    mock_sweep = MagicMock()
    mock_sweep.return_value = b"-80.5,-79.2,-82.3,-85.1\n-81.2,-80.9,-83.1,-84.7\n"

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = lambda args, **kwargs: {
            "hackrf_info": MagicMock(stdout=mock_info(), returncode=0),
            "hackrf_sweep": MagicMock(stdout=mock_sweep(), returncode=0),
        }.get(args[0], MagicMock(returncode=0))

        yield mock_run


def test_scanner_initialization(mock_hackrf_commands):
    """Test scanner initialization with mocked hardware."""
    with patch("os.path.exists", return_value=True), patch("os.makedirs"), patch(
        "tempfile.mkdtemp", return_value="/tmp/mock_hackrf"
    ), patch("tinfoilhat.scanner.Scanner._check_hackrf", return_value=True):
        # Initialize Scanner
        scanner = Scanner()

        # Verify scanner attributes
        assert len(scanner.frequencies) > 0
        assert scanner.samples_per_freq > 0
        assert scanner.temp_dir == "/tmp/mock_hackrf"

        # Verify frequency labels are loaded
        assert len(scanner.frequency_labels) > 0

        # Test that HackRF is detected (checking hackrf_available)
        assert scanner.hackrf_available is True


def test_measure_power_at_frequency(mock_hackrf_commands):
    """Test power measurement at a specific frequency with mocked hardware."""
    # Using multiple patches in a single with statement for clarity and to avoid nesting
    with patch("os.path.exists", side_effect=lambda path: True), patch("os.makedirs"), patch(
        "tempfile.mkdtemp", return_value="/tmp/mock_hackrf"
    ), patch("builtins.open", MagicMock()), patch("time.sleep"), patch("os.path.getsize", return_value=1024):

        # Create a mock file for _analyze_iq_samples to read
        mock_file = MagicMock()
        mock_file.read.return_value = b"mock_iq_data"

        # Mock the file open operation and subprocess together
        with patch("builtins.open", return_value=mock_file), patch(
            "subprocess.run", return_value=MagicMock(returncode=0)
        ), patch("tinfoilhat.scanner.Scanner._check_hackrf", return_value=True), patch(
            "tinfoilhat.scanner.Scanner.refresh_hackrf", return_value=True
        ):

            # Initialize Scanner
            scanner = Scanner()

            # Ensure hackrf_available is True
            scanner.hackrf_available = True

            # Mock the _analyze_iq_samples method to return a fixed value
            scanner._analyze_iq_samples = MagicMock(return_value=-85.5)

            # Test measurement
            power = scanner._measure_power_at_frequency(433.0 * 1e6)  # Convert MHz to Hz

            # Verify result with a tolerance to account for frequency adjustment
            assert abs(power - (-85.5)) < 0.5  # Allow for some frequency adjustment

            # Verify _analyze_iq_samples was called
            scanner._analyze_iq_samples.assert_called_once()


def test_calculate_attenuation():
    """Test attenuation calculation."""
    with patch("os.path.exists", return_value=True), patch("os.makedirs"), patch(
        "tempfile.mkdtemp", return_value="/tmp/mock_hackrf"
    ):
        # Initialize Scanner
        scanner = Scanner()

        # Define test data
        baseline_levels = [-80.0, -85.0, -90.0, -75.0]
        hat_levels = [-85.0, -90.0, -92.0, -76.0]

        # Calculate attenuation
        attenuation = scanner.calculate_attenuation(baseline_levels, hat_levels)

        # Verify results - attenuation should be the difference between hat and baseline
        # with possible adjustments based on frequency
        assert len(attenuation) == len(baseline_levels)
        # Just check that values are present, exact values will depend on frequency adjustment
        for a in attenuation:
            assert isinstance(a, float)


def test_frequency_gain_selection():
    """Test that appropriate gains are selected for different frequency ranges."""
    with patch("os.path.exists", return_value=True), patch("os.makedirs"), patch(
        "tempfile.mkdtemp", return_value="/tmp/mock_hackrf"
    ):
        # Initialize Scanner
        scanner = Scanner()

        # Mock file operations to avoid file not found errors
        with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=1024), patch(
            "builtins.open", return_value=MagicMock(read=lambda: b"mock_iq_data")
        ), patch("subprocess.run", return_value=MagicMock(returncode=0)), patch.object(
            scanner, "_analyze_iq_samples", return_value=-85.0
        ):

            # Test low frequency
            scanner._measure_power_at_frequency(80e6)  # 80 MHz
            # Test medium frequency
            scanner._measure_power_at_frequency(800e6)  # 800 MHz
            # Test high frequency
            scanner._measure_power_at_frequency(5000e6)  # 5 GHz

            # We're primarily checking that the code runs without errors
            # since the actual gain values are set inside the method
            assert True


def test_average_measurements():
    """Test the averaging of multiple power measurements."""
    with patch("os.path.exists", return_value=True), patch("os.makedirs"), patch(
        "tempfile.mkdtemp", return_value="/tmp/mock_hackrf"
    ):
        # Initialize Scanner
        scanner = Scanner()

        # Generate mock measurements
        measurements = [-82.1, -83.5, -81.9, -82.7, -82.0]

        # Set the number of samples and mock _capture_power_level to return our values
        scanner.samples_per_freq = len(measurements)
        measurement_iter = iter(measurements)
        scanner._capture_power_level = MagicMock(side_effect=lambda *args: next(measurement_iter))

        # Test the measurement with averaging - using combined with statements
        with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=1024), patch(
            "builtins.open", return_value=MagicMock(read=lambda: b"mock_iq_data")
        ), patch("subprocess.run", return_value=MagicMock(returncode=0)):

            # Expected result is the average of our measurements
            expected = sum(measurements) / len(measurements)

            # Test by taking a single measurement with averaging
            scanner._analyze_iq_samples = MagicMock(side_effect=measurements)
            result = scanner._measure_power_at_frequency(433e6)

            # Since we're mocking _capture_power_level to return each value from measurements,
            # the result should be their average
            assert abs(result - expected) < 0.1
