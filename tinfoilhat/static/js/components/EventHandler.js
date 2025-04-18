/**
 * EventHandler.js
 * Handles Server-Sent Events (SSE) and event processing
 */

class EventHandler {
    constructor(chartManager, dataManager, leaderboardManager, uiManager, errorHandler) {
        this.chartManager = chartManager;
        this.dataManager = dataManager;
        this.leaderboardManager = leaderboardManager;
        this.uiManager = uiManager;
        this.errorHandler = errorHandler;
        
        this.eventSource = null;
        this.frequencyEventSource = null;
        this.lastId = 0;
        this.usePolling = false;
        this.pollingInterval = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000; // 3 seconds
        
        // Create safe versions of critical methods
        if (this.errorHandler) {
            this.handleBillboardUpdate = this.errorHandler.makeSafe(
                this, 'EventHandler', 'handleBillboardUpdate', this.handleBillboardUpdate
            );
            
            this.handleFrequencyEvent = this.errorHandler.makeSafe(
                this, 'EventHandler', 'handleFrequencyEvent', this.handleFrequencyEvent
            );
            
            this.handleReset = this.errorHandler.makeSafe(
                this, 'EventHandler', 'handleReset', this.handleReset
            );
            
            this.handleTestCompletion = this.errorHandler.makeSafe(
                this, 'EventHandler', 'handleTestCompletion', this.handleTestCompletion
            );
        }
    }

    /**
     * Initialize SSE connection
     * @param {number} lastId - Last event ID received
     */
    setupSSE(lastId = 0) {
        this.lastId = lastId;
        
        try {
            // Close any existing connections
            this.closeConnections();
            
            // Main leaderboard updates
            this.eventSource = new EventSource(`/billboard-updates?last_id=${this.lastId}`);
            
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Received SSE message:', data);
                    this.handleBillboardUpdate(data);
                    this.lastId = data.last_id;
                } catch (error) {
                    if (this.errorHandler) {
                        this.errorHandler.handleError('EventHandler', 'eventSource.onmessage', error);
                    } else {
                        console.error('Error handling billboard update:', error);
                    }
                }
            };
            
            this.eventSource.onerror = (e) => {
                if (this.errorHandler) {
                    this.errorHandler.handleError('EventHandler', 'eventSource.onerror', 
                        'SSE connection error, falling back to polling...', 'warning');
                } else {
                    console.log('SSE connection error, falling back to polling...');
                }
                this.eventSource.close();
                this.usePolling = true;
                this.startPolling();
            };
            
            // Real-time frequency measurement updates
            this.frequencyEventSource = new EventSource('/frequency-stream');
            
            this.frequencyEventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Frequency stream event received:', data);
                    this.handleFrequencyEvent(data);
                } catch (error) {
                    if (this.errorHandler) {
                        this.errorHandler.handleError('EventHandler', 'frequencyEventSource.onmessage', error);
                    } else {
                        console.error('Error handling frequency event:', error);
                    }
                }
            };
            
            this.frequencyEventSource.onerror = (e) => {
                // Log the error
                if (this.errorHandler) {
                    this.errorHandler.handleError('EventHandler', 'frequencyEventSource.onerror', 
                        'Frequency stream connection error', 'warning');
                } else {
                    console.log('Frequency stream connection error');
                }
                
                this.frequencyEventSource.close();
                
                // Implement exponential backoff for reconnection
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
                    console.log(`Attempting to reconnect in ${delay/1000} seconds (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                    
                    setTimeout(() => {
                        try {
                            this.frequencyEventSource = new EventSource('/frequency-stream');
                            // Reset reconnect attempts on successful connection
                            this.frequencyEventSource.onopen = () => {
                                this.reconnectAttempts = 0;
                                console.log('Frequency stream reconnection successful');
                            };
                            
                            // Re-attach event handlers
                            this.frequencyEventSource.onmessage = this.frequencyEventSource.onmessage;
                            this.frequencyEventSource.onerror = this.frequencyEventSource.onerror;
                        } catch (error) {
                            if (this.errorHandler) {
                                this.errorHandler.handleError('EventHandler', 'frequencyEventSource.reconnect', error);
                            }
                        }
                    }, delay);
                } else {
                    // Max retries exceeded, show error and fall back to polling
                    console.error('Max reconnection attempts exceeded for frequency stream');
                    this.uiManager.showNotification(
                        'Connection to the measurement stream has been lost. Data updates will be delayed.',
                        'error', 
                        0
                    );
                }
            };
        } catch (e) {
            if (this.errorHandler) {
                this.errorHandler.handleError('EventHandler', 'setupSSE', e);
            } else {
                console.log('Error setting up SSE, falling back to polling:', e);
            }
            this.usePolling = true;
            this.startPolling();
        }
    }

    /**
     * Close all event source connections
     */
    closeConnections() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        if (this.frequencyEventSource) {
            this.frequencyEventSource.close();
            this.frequencyEventSource = null;
        }
        
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    /**
     * Start polling for updates (fallback if SSE fails)
     */
    startPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        
        this.pollingInterval = setInterval(() => {
            fetch(`/billboard-updates?last_id=${this.lastId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! Status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    this.handleBillboardUpdate(data);
                    this.lastId = data.last_id;
                })
                .catch(error => {
                    if (this.errorHandler) {
                        this.errorHandler.handleError('EventHandler', 'startPolling.fetch', error);
                    } else {
                        console.error('Error polling for updates:', error);
                    }
                });
        }, 5000); // Poll every 5 seconds
    }

    /**
     * Centralized method to handle reset operations
     * @param {Object} data - Data object containing reset information
     * @param {boolean} isEmergency - Whether this is an emergency reset
     */
    handleReset(data, isEmergency = false) {
        if (isEmergency) {
            console.log("🔥🔥🔥 EMERGENCY RESET DETECTED - FORCING IMMEDIATE CHART RESET 🔥🔥🔥");
            this.uiManager.showEmergencyReset();
        } else {
            console.log("🔄🔄🔄 RESET DETECTED - CLEARING ALL CHART DATA 🔄🔄🔄");
        }
        
        // Reset the chart
        this.chartManager.resetChart();
        
        // Reset the data manager
        this.dataManager.resetData();
        
        // Update UI to indicate reset
        if (data.baseline_start === true || (data.new_test && data.new_test.is_baseline_start === true)) {
            this.uiManager.showBaselineInProgress();
            
            // Set baseline_in_progress flag in data manager
            this.dataManager.currentTestData.measurement_type = 'baseline';
            this.dataManager.currentTestData.baseline_in_progress = true;
        } else {
            this.uiManager.showDataReset();
        }
        
        // Add a visual reset notification
        this.uiManager.showResetNotificationInUI();
    }

    /**
     * Centralized method to handle test completion
     * @param {Object} data - Test completion data
     */
    handleTestCompletion(data) {
        console.log("🏆 TEST COMPLETION EVENT RECEIVED - Updating recent test and leaderboards");
        
        // Create a test object from the test completion data
        const testData = {
            name: data.contestant_name || "Unknown",
            hat_type: data.hat_type ? (data.hat_type.charAt(0).toUpperCase() + data.hat_type.slice(1)) : "Classic",
            attenuation: parseFloat(data.average_attenuation || 0),
            date: new Date().toLocaleString()
        };
        
        // Update the recent test display
        this.uiManager.updateRecentTest(testData);
        
        // Update leaderboards if they're included in the event
        if (data.leaderboard_classic) {
            this.leaderboardManager.updateLeaderboard('classic', data.leaderboard_classic);
        }
        
        if (data.leaderboard_hybrid) {
            this.leaderboardManager.updateLeaderboard('hybrid', data.leaderboard_hybrid);
        }
    }

    /**
     * Handle billboard update event
     * @param {Object} data - Billboard update data
     */
    handleBillboardUpdate(data) {
        // Log the entire data object for debugging
        console.log("============== BILLBOARD UPDATE =============");
        console.log("Received billboard update with data:", data);
        console.log("============================================");
        
        // Check for reset events or the start of a new baseline test
        const isReset = data.reset === true || 
                       (data.spectrum_data && data.spectrum_data.test_state === 'reset') ||
                       (data.event_type === 'test_reset' || data.event_type === 'clear_all') ||
                       (data.new_test && data.new_test.is_baseline_start === true);
        
        if (isReset) {
            this.handleReset(data);
        }
        
        // Check for test completion events
        if (data.event_type === "test_complete") {
            this.handleTestCompletion(data);
        }
        
        // Update the recent test display if there's new test data
        if (data.new_test) {
            this.uiManager.updateRecentTest(data.new_test);
            
            // IMPORTANT: Modified the data preservation behavior
            // We now only preserve measurement-specific fields if NOT a reset
            if (!isReset) {
                // This is a normal test completion, we can keep frequency data
                this.dataManager.currentTestData.measurement_type = null;
                this.dataManager.currentTestData.contestant_id = null;
                this.dataManager.currentTestData.contestant_name = null;
                this.dataManager.currentTestData.hat_type = null;
                this.dataManager.currentTestData.baseline_in_progress = false;
                // We keep frequencies[], baseline_levels[], hat_levels[], and attenuations[] intact
            }
        }
        
        // Update leaderboards
        if (data.leaderboard_classic) {
            this.leaderboardManager.updateLeaderboard('classic', data.leaderboard_classic);
        }
        
        if (data.leaderboard_hybrid) {
            this.leaderboardManager.updateLeaderboard('hybrid', data.leaderboard_hybrid);
        }
        
        // Store frequency labels if available for chart tooltips and axis labels
        if (data.frequency_labels) {
            console.log("Received frequency labels:", data.frequency_labels);
            this.dataManager.setFrequencyLabels(data.frequency_labels);
            this.chartManager.updateChartCallbacks(data.frequency_labels);
        }
        
        // Update charts with spectrum data ONLY if there's meaningful data
        if (data.spectrum_data && Object.keys(data.spectrum_data).length > 0) {
            console.log("Received spectrum data:", data.spectrum_data);
            
            // If this is a reset, we will always update chart (removing old data)
            // For normal updates, we still preserve good frequency data                    
            if (!isReset && data.new_test) {
                // Check if data has missing/bad frequencies
                const hasBadFrequencies = !data.spectrum_data.frequencies || 
                                         data.spectrum_data.frequencies.length === 0 || 
                                         data.spectrum_data.frequencies.every(f => f === 0 || f === '0' || f === '0.0');
                
                if (hasBadFrequencies) {
                    console.warn("Test completion data has missing or zero frequencies - keeping current chart display");
                    return; // Don't update the chart at all, keep showing what we already have
                }
            }
            
            // Create a copy of spectrum data to work with
            const updatedSpectrumData = {...data.spectrum_data};
            
            // Check if frequencies are missing or empty in the incoming data
            if (!updatedSpectrumData.frequencies || updatedSpectrumData.frequencies.length === 0) {
                console.warn("Missing frequencies in spectrum data - using saved frequencies from current test data");
                
                // Use frequencies from currentTestData if available
                const currentData = this.dataManager.getCurrentTestData();
                if (currentData.frequencies && currentData.frequencies.length > 0) {
                    updatedSpectrumData.frequencies = [...currentData.frequencies];
                    console.log("Using saved frequencies:", updatedSpectrumData.frequencies);
                } else {
                    console.error("No frequency data available - cannot update chart");
                    return;
                }
            }
            
            // Ensure other required arrays exist and have correct length
            const freqLength = updatedSpectrumData.frequencies.length;
            const currentData = this.dataManager.getCurrentTestData();
            
            // Check baseline levels
            if (!updatedSpectrumData.baseline_levels || updatedSpectrumData.baseline_levels.length !== freqLength) {
                if (currentData.baseline_levels && currentData.baseline_levels.length === freqLength) {
                    updatedSpectrumData.baseline_levels = [...currentData.baseline_levels];
                } else {
                    updatedSpectrumData.baseline_levels = Array(freqLength).fill(-85); // Default value
                }
            }
            
            // Check hat levels
            if (!updatedSpectrumData.hat_levels || updatedSpectrumData.hat_levels.length !== freqLength) {
                if (currentData.hat_levels && currentData.hat_levels.length === freqLength) {
                    updatedSpectrumData.hat_levels = [...currentData.hat_levels];
                } else {
                    updatedSpectrumData.hat_levels = Array(freqLength).fill(-85); // Default value
                }
            }
            
            // Check attenuations
            if (!updatedSpectrumData.attenuations || updatedSpectrumData.attenuations.length !== freqLength) {
                if (currentData.attenuations && currentData.attenuations.length === freqLength) {
                    updatedSpectrumData.attenuations = [...currentData.attenuations];
                } else {
                    // Calculate attenuations if possible
                    updatedSpectrumData.attenuations = Array(freqLength).fill(0);
                    for (let i = 0; i < freqLength; i++) {
                        if (updatedSpectrumData.baseline_levels[i] !== null && updatedSpectrumData.hat_levels[i] !== null) {
                            updatedSpectrumData.attenuations[i] = updatedSpectrumData.baseline_levels[i] - updatedSpectrumData.hat_levels[i];
                        }
                    }
                }
            }
            
            // Ensure frequencies are properly formatted as numbers
            updatedSpectrumData.frequencies = updatedSpectrumData.frequencies.map(f => 
                typeof f === 'string' ? parseFloat(f) : f
            );
            
            // Update the chart with our complete data
            this.chartManager.updateChart(updatedSpectrumData);
            
            // Save a copy of the data for future use
            this.dataManager.updateWithSpectrumData(updatedSpectrumData);
        }
    }

    /**
     * Handle frequency event
     * @param {Object} data - Frequency event data
     */
    handleFrequencyEvent(data) {
        // Check if this is a reset event (highest priority)
        if (data.event_type === 'clear_all' || data.event_type === 'test_reset') {
            const isEmergency = data.emergency === true;
            this.handleReset(data, isEmergency);
            return;
        }
        
        // Check for test completion events
        if (data.event_type === 'test_complete') {
            this.handleTestCompletion(data);
            return;
        }
        
        // Handle billboard update events with spectrum data
        if (data.event_type === 'billboard_update') {
            // This is a special update for the billboard with spectrum data
            console.log('Billboard update received:', data);
            
            // If this update includes spectrum data, update the chart
            if (data.spectrum_data) {
                // Check if this is a reset event
                if (data.spectrum_data.test_state === "reset") {
                    this.handleReset(data);
                    return;
                }
                // Update with new spectrum data if it contains frequencies
                else if (data.spectrum_data.frequencies && data.spectrum_data.frequencies.length > 0) {
                    // Update chart with spectrum data
                    this.chartManager.updateChart(data.spectrum_data);
                    
                    // Also update data manager
                    this.dataManager.updateWithSpectrumData(data.spectrum_data);
                }
            }
            
            return;
        }
        
        // This is a single frequency measurement update
        console.log('Frequency update:', data);
        
        // Check for first baseline measurement
        if (this.dataManager.isFirstBaselineMeasurement(data)) {
            console.log("🔄 First baseline measurement detected - clearing all previous data");
            
            // Reset chart
            this.chartManager.resetChart();
            
            // Reset data manager with baseline info
            this.dataManager.resetData();
            this.dataManager.currentTestData.measurement_type = 'baseline';
            this.dataManager.currentTestData.contestant_id = data.contestant_id || null;
            this.dataManager.currentTestData.contestant_name = data.contestant_name || "Baseline Measurement";
            this.dataManager.currentTestData.hat_type = data.hat_type || null;
            this.dataManager.currentTestData.baseline_in_progress = true;
            
            // Update UI
            this.uiManager.showFirstBaselineMeasurement();
        }
        
        // Process measurement data
        const dataProcessed = this.dataManager.handleFrequencyMeasurement(data);
        
        if (dataProcessed) {
            // Update the recent test information with current test data
            this.uiManager.updateRecentTestWithCurrentData(this.dataManager.getCurrentTestData());
            
            // Update the chart with live data
            const currentData = this.dataManager.getCurrentTestData();
            this.chartManager.updateWithLiveData(
                currentData.frequencies,
                currentData.baseline_levels,
                currentData.hat_levels,
                currentData.attenuations
            );
        }
    }
}

// Export the EventHandler class
window.EventHandler = EventHandler; 