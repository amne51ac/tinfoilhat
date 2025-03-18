"""
Scanner module for the Tinfoil Hat Competition application.

This module handles communication with the HackRF One device and processes
signal measurements.
"""

import random
import time
from typing import List, Optional, Tuple

import numpy as np

# In a production environment, we would use the pyrtlsdr library
# to communicate with the HackRF One. For development and testing,
# we'll use a simulated scanner that generates random data.


class Scanner:
    """
    Scanner class to interface with the HackRF One device.
    
    This class manages signal measurements for the tinfoil hat competition.
    In real usage, this would communicate with a HackRF One device,
    but for development we simulate the results.
    """
    
    def __init__(self, num_frequencies: int = 50, min_freq: int = 50e6, max_freq: int = 6e9, samples_per_freq: int = 100):
        """
        Initialize the scanner with frequency range.
        
        :param num_frequencies: Number of frequencies to test, defaults to 50
        :type num_frequencies: int, optional
        :param min_freq: Minimum frequency in Hz, defaults to 50MHz
        :type min_freq: int, optional
        :param max_freq: Maximum frequency in Hz, defaults to 6GHz
        :type max_freq: int, optional
        :param samples_per_freq: Number of samples to take per frequency, defaults to 100
        :type samples_per_freq: int, optional
        """
        self.num_frequencies = num_frequencies
        self.min_freq = min_freq
        self.max_freq = max_freq
        self.samples_per_freq = samples_per_freq
        
        # Generate logarithmically spaced frequencies
        self.frequencies = np.logspace(
            np.log10(min_freq),
            np.log10(max_freq),
            num_frequencies
        ).astype(int).tolist()
    
    def _init_device(self) -> bool:
        """
        Initialize the HackRF One device.
        
        In a real implementation, this would connect to the HackRF One.
        For development, we just simulate a delay.
        
        :return: True if device initialized successfully
        :rtype: bool
        """
        # Simulate device initialization
        time.sleep(0.5)
        return True
    
    def _take_single_reading(self, frequency: int, is_hat_measurement: bool = False) -> float:
        """
        Take a single reading at a specific frequency.
        
        In a real implementation, this would take an actual measurement from the HackRF One.
        For development, we generate a random value within a realistic range.
        
        :param frequency: Frequency to measure in Hz
        :type frequency: int
        :param is_hat_measurement: Whether this is a hat measurement (vs baseline), defaults to False
        :type is_hat_measurement: bool, optional
        :return: Simulated noise level reading in dBm
        :rtype: float
        """
        # For baseline readings, simulate noise levels between -80 and -70 dBm
        if not is_hat_measurement:
            return random.uniform(-80, -70)
        # For hat readings, simulate levels between -100 and -80 dBm (better attenuation)
        else:
            return random.uniform(-100, -80)
    
    def get_baseline_readings(self) -> List[float]:
        """
        Get baseline readings without a tinfoil hat.
        
        Takes multiple samples per frequency and averages them for more stable readings.
        
        :return: List of average noise levels at each frequency
        :rtype: List[float]
        """
        self._init_device()
        
        # Take multiple samples at each frequency and average them
        baseline = []
        for freq in self.frequencies:
            # Take multiple readings at this frequency
            readings = [self._take_single_reading(freq) for _ in range(self.samples_per_freq)]
            # Calculate the average reading for this frequency
            avg_reading = sum(readings) / len(readings)
            baseline.append(avg_reading)
        
        return baseline
    
    def get_hat_readings(self) -> List[float]:
        """
        Get readings with a tinfoil hat on the mannequin.
        
        Takes multiple samples per frequency and averages them for more stable readings.
        
        :return: List of average noise levels at each frequency with hat
        :rtype: List[float]
        """
        self._init_device()
        
        # Take multiple samples at each frequency and average them
        hat_readings = []
        for freq in self.frequencies:
            # Take multiple readings at this frequency
            readings = [self._take_single_reading(freq, is_hat_measurement=True) for _ in range(self.samples_per_freq)]
            # Calculate the average reading for this frequency
            avg_reading = sum(readings) / len(readings)
            hat_readings.append(avg_reading)
        
        return hat_readings
    
    def calculate_attenuation(self, baseline: List[float], hat_readings: List[float]) -> List[float]:
        """
        Calculate attenuation at each frequency by comparing baseline to hat readings.
        
        :param baseline: Baseline readings without hat
        :type baseline: List[float]
        :param hat_readings: Readings with hat
        :type hat_readings: List[float]
        :return: Attenuation values at each frequency
        :rtype: List[float]
        """
        # Attenuation is the difference between baseline and hat readings
        # A positive value means the hat reduced the signal (good)
        attenuation = []
        for base, hat in zip(baseline, hat_readings):
            # Lower hat reading means better attenuation (more negative dBm)
            # So we subtract hat from baseline to get positive attenuation values
            att = base - hat
            attenuation.append(att)
        
        return attenuation 