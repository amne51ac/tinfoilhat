/**
 * DataManager.js
 * Handles test data management and tracking
 */

class DataManager {
    constructor(errorHandler) {
        // Create object to store the current test data
        this.currentTestData = this.getEmptyTestData();
        this.frequencyLabels = {};
        this.errorHandler = errorHandler;
        
        // Create safe versions of critical methods
        if (this.errorHandler) {
            this.handleFrequencyMeasurement = this.errorHandler.makeSafe(
                this, 'DataManager', 'handleFrequencyMeasurement', this.handleFrequencyMeasurement
            );
            this.updateWithSpectrumData = this.errorHandler.makeSafe(
                this, 'DataManager', 'updateWithSpectrumData', this.updateWithSpectrumData
            );
        }
    }

    /**
     * Get an empty test data object
     * @returns {Object} Empty test data object
     */
    getEmptyTestData() {
        return {
            frequencies: [],
            baseline_levels: [],
            hat_levels: [],
            attenuations: [],
            measurement_type: null,
            contestant_id: null,
            contestant_name: null,
            hat_type: null,
            baseline_in_progress: false
        };
    }

    /**
     * Reset all test data to empty state
     */
    resetData() {
        try {
            this.currentTestData = this.getEmptyTestData();
        } catch (error) {
            if (this.errorHandler) {
                this.errorHandler.handleError('DataManager', 'resetData', error);
            } else {
                console.error('Error resetting data:', error);
            }
        }
    }

    /**
     * Store frequency labels for use in chart tooltips and axis labels
     * @param {Object} labels - Frequency labels
     */
    setFrequencyLabels(labels) {
        try {
            if (!labels) {
                if (this.errorHandler) {
                    this.errorHandler.handleError('DataManager', 'setFrequencyLabels', 
                        'Invalid frequency labels', 'warning');
                }
                return;
            }
            this.frequencyLabels = labels;
        } catch (error) {
            if (this.errorHandler) {
                this.errorHandler.handleError('DataManager', 'setFrequencyLabels', error);
            } else {
                console.error('Error setting frequency labels:', error);
            }
        }
    }

    /**
     * Get the current frequency labels
     * @returns {Object} Frequency labels
     */
    getFrequencyLabels() {
        return this.frequencyLabels;
    }

    /**
     * Handle a new frequency measurement
     * @param {Object} data - Measurement data
     * @returns {boolean} True if data was processed
     */
    handleFrequencyMeasurement(data) {
        try {
            if (!data || (!data.frequency_mhz && data.frequency_mhz !== 0)) {
                if (this.errorHandler) {
                    this.errorHandler.handleError('DataManager', 'handleFrequencyMeasurement', 
                        'Invalid frequency measurement data', 'warning');
                }
                return false;
            }
            
            // Store contestant information if available
            if (data.contestant_id && !this.currentTestData.contestant_id) {
                this.currentTestData.contestant_id = data.contestant_id;
            }
            
            // Store contestant name and hat type if available
            if (data.contestant_name) {
                this.currentTestData.contestant_name = data.contestant_name;
            }
            
            if (data.hat_type) {
                this.currentTestData.hat_type = data.hat_type;
            }
            
            // Update measurement type
            this.currentTestData.measurement_type = data.measurement_type;
            
            // Check if this is a baseline measurement
            if (data.measurement_type === 'baseline') {
                return this.handleBaselineMeasurement(data);
            } 
            // Check if this is a hat measurement
            else if (data.measurement_type === 'hat') {
                return this.handleHatMeasurement(data);
            }
            
            return false;
        } catch (error) {
            if (this.errorHandler) {
                this.errorHandler.handleError('DataManager', 'handleFrequencyMeasurement', error);
            } else {
                console.error('Error handling frequency measurement:', error);
            }
            return false;
        }
    }

    /**
     * Handle a baseline measurement
     * @param {Object} data - Measurement data
     * @returns {boolean} True if data was processed
     */
    handleBaselineMeasurement(data) {
        // Set the baseline in progress flag
        this.currentTestData.baseline_in_progress = true;
    
        // Store baseline measurement
        const freqIndex = this.currentTestData.frequencies.indexOf(data.frequency_mhz);
        if (freqIndex === -1) {
            // New frequency
            this.currentTestData.frequencies.push(data.frequency_mhz);
            this.currentTestData.baseline_levels.push(data.power);
            
            // Sort the arrays by frequency
            const sortIndices = [...this.currentTestData.frequencies.keys()]
                .sort((a, b) => this.currentTestData.frequencies[a] - this.currentTestData.frequencies[b]);
            
            this.currentTestData.frequencies = sortIndices.map(i => this.currentTestData.frequencies[i]);
            this.currentTestData.baseline_levels = sortIndices.map(i => this.currentTestData.baseline_levels[i]);
            
            // Add placeholder null values for hat and attenuation
            if (this.currentTestData.hat_levels.length < this.currentTestData.frequencies.length) {
                this.currentTestData.hat_levels.push(null);
                this.currentTestData.attenuations.push(null);
            }
        } else {
            // Update existing frequency
            this.currentTestData.baseline_levels[freqIndex] = data.power;
        }
        
        return true;
    }

    /**
     * Handle a hat measurement
     * @param {Object} data - Measurement data
     * @returns {boolean} True if data was processed
     */
    handleHatMeasurement(data) {
        // If we're switching from baseline to hat, update the flag
        if (this.currentTestData.baseline_in_progress) {
            this.currentTestData.baseline_in_progress = false;
        }
        
        // Store hat measurement and attenuation if available
        const freqIndex = this.currentTestData.frequencies.indexOf(data.frequency_mhz);
        if (freqIndex === -1) {
            // New frequency
            this.currentTestData.frequencies.push(data.frequency_mhz);
            this.currentTestData.hat_levels.push(data.power);
            this.currentTestData.attenuations.push(data.attenuation || null);
            
            // Add placeholder null value for baseline if needed
            if (this.currentTestData.baseline_levels.length < this.currentTestData.frequencies.length) {
                this.currentTestData.baseline_levels.push(null);
            }
            
            // Sort the arrays by frequency
            const sortIndices = [...this.currentTestData.frequencies.keys()]
                .sort((a, b) => this.currentTestData.frequencies[a] - this.currentTestData.frequencies[b]);
            
            this.currentTestData.frequencies = sortIndices.map(i => this.currentTestData.frequencies[i]);
            this.currentTestData.baseline_levels = sortIndices.map(i => this.currentTestData.baseline_levels[i]);
            this.currentTestData.hat_levels = sortIndices.map(i => this.currentTestData.hat_levels[i]);
            this.currentTestData.attenuations = sortIndices.map(i => this.currentTestData.attenuations[i]);
        } else {
            // Update existing frequency
            this.currentTestData.hat_levels[freqIndex] = data.power;
            this.currentTestData.attenuations[freqIndex] = data.attenuation || null;
        }
        
        return true;
    }

    /**
     * Check if this is the first baseline measurement of a new test
     * @param {Object} data - Measurement data
     * @returns {boolean} True if this is the first baseline measurement
     */
    isFirstBaselineMeasurement(data) {
        return data.measurement_type === 'baseline' && 
            (this.currentTestData.frequencies.length === 0 || 
             data.first_measurement === true || 
             (this.currentTestData.hat_levels.some(level => level !== null) && 
              !this.currentTestData.baseline_in_progress));
    }

    /**
     * Update test data with new spectrum data
     * @param {Object} spectrumData - Spectrum data
     */
    updateWithSpectrumData(spectrumData) {
        try {
            if (!spectrumData || !spectrumData.frequencies || spectrumData.frequencies.length === 0) {
                if (this.errorHandler) {
                    this.errorHandler.handleError('DataManager', 'updateWithSpectrumData', 
                        'Invalid spectrum data', 'warning');
                }
                return false;
            }
            
            this.currentTestData.frequencies = [...spectrumData.frequencies];
            
            if (spectrumData.baseline_levels) {
                this.currentTestData.baseline_levels = [...spectrumData.baseline_levels];
            }
            
            if (spectrumData.hat_levels) {
                this.currentTestData.hat_levels = [...spectrumData.hat_levels];
            }
            
            if (spectrumData.attenuations) {
                this.currentTestData.attenuations = [...spectrumData.attenuations];
            }
            
            return true;
        } catch (error) {
            if (this.errorHandler) {
                this.errorHandler.handleError('DataManager', 'updateWithSpectrumData', error);
            } else {
                console.error('Error updating with spectrum data:', error);
            }
            return false;
        }
    }

    /**
     * Calculate average attenuation from the current test data
     * @returns {number} Average attenuation
     */
    calculateAverageAttenuation() {
        const validAttenuations = this.currentTestData.attenuations.filter(a => a !== null);
        if (validAttenuations.length === 0) return 0;
        
        return validAttenuations.reduce((sum, val) => sum + val, 0) / validAttenuations.length;
    }

    /**
     * Get the current test data
     * @returns {Object} Current test data
     */
    getCurrentTestData() {
        return this.currentTestData;
    }
}

// Export the DataManager class
window.DataManager = DataManager; 