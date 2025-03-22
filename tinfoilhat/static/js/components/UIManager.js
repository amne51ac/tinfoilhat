/**
 * UIManager.js
 * Handles UI updates and interactions
 */

class UIManager {
    constructor() {
        this.recentTestElement = document.getElementById('recent-test');
        this.terminalTimeElement = document.getElementById('terminal-time');
        
        // Start terminal time updates
        this.startTerminalTimeUpdates();
    }

    /**
     * Start updating the terminal time display
     */
    startTerminalTimeUpdates() {
        this.updateTerminalTime();
        setInterval(() => this.updateTerminalTime(), 1000);
    }

    /**
     * Update the terminal time display
     */
    updateTerminalTime() {
        if (!this.terminalTimeElement) return;
        
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-US', { 
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        this.terminalTimeElement.textContent = timeStr;
    }

    /**
     * Update the recent test display with current test data
     * @param {Object} testData - Current test data
     */
    updateRecentTestWithCurrentData(testData) {
        if (!this.recentTestElement) return;
        
        const testInfo = this.recentTestElement.querySelector('.test-info');
        if (!testInfo) return;

        // Set contestant name (use "Baseline" if in baseline measurement mode)
        let displayName = "Unknown";
        if (testData.measurement_type === 'baseline') {
            displayName = "Baseline";
        } else if (testData.contestant_name) {
            displayName = testData.contestant_name;
        }
        
        // Set hat type
        let hatTypeDisplay = "Measuring...";
        if (testData.hat_type) {
            hatTypeDisplay = testData.hat_type.charAt(0).toUpperCase() + 
                            testData.hat_type.slice(1) + " Hat";
        } else if (testData.measurement_type === 'baseline') {
            hatTypeDisplay = "Baseline Measurement";
        }
        
        // Calculate average attenuation from valid values
        let avgAttenuation = 0;
        let validAttenuations = testData.attenuations.filter(a => a !== null);
        if (validAttenuations.length > 0) {
            avgAttenuation = validAttenuations.reduce((sum, val) => sum + val, 0) / validAttenuations.length;
        }
        
        // Create HTML for recent test
        testInfo.innerHTML = `
            <div class="contestant-name">${displayName}</div>
            <div class="hat-type">${hatTypeDisplay}</div>
            <div class="attenuation ${avgAttenuation < 0 ? 'negative-attenuation' : ''}">
                ${avgAttenuation.toFixed(2)} dB
            </div>
            <div class="test-date">In Progress</div>
        `;
        
        // Add the "measurement in progress" indicator if it doesn't exist
        if (!this.recentTestElement.querySelector('.test-in-progress')) {
            const testInProgress = document.createElement('div');
            testInProgress.className = 'test-in-progress';
            testInProgress.innerHTML = '<div class="measuring-indicator">MEASUREMENT IN PROGRESS</div>';
            testInfo.appendChild(testInProgress);
        }
    }

    /**
     * Update the recent test display with completed test data
     * @param {Object} testData - Completed test data
     */
    updateRecentTest(testData) {
        if (!this.recentTestElement) return;
        
        const testInfo = this.recentTestElement.querySelector('.test-info');
        if (!testInfo) return;
        
        console.log("Updating recent test display with:", testData);
        
        // No animation class, just update content
        testInfo.innerHTML = `
            <div class="contestant-name">${testData.name}</div>
            <div class="hat-type">${testData.hat_type.charAt(0).toUpperCase() + testData.hat_type.slice(1)} Hat</div>
            <div class="attenuation ${testData.attenuation < 0 ? 'negative-attenuation' : ''}">
                ${parseFloat(testData.attenuation).toFixed(2)} dB
            </div>
            <div class="test-date">${testData.date}</div>
        `;
        
        // Remove any "in progress" indicators
        this.removeInProgressIndicator();
    }

    /**
     * Show baseline test in progress state
     */
    showBaselineInProgress() {
        if (!this.recentTestElement) return;
        
        const testInfo = this.recentTestElement.querySelector('.test-info');
        if (!testInfo) return;
        
        // Show baseline in progress message
        testInfo.innerHTML = `
            <div class="contestant-name">BASELINE TEST</div>
            <div class="hat-type">Baseline Measurement in Progress</div>
            <div class="attenuation">0.00 dB</div>
            <div class="test-date">In Progress</div>
        `;
        
        // Add a baseline in progress indicator
        const testInProgress = document.createElement('div');
        testInProgress.className = 'test-in-progress';
        testInProgress.innerHTML = '<div class="measuring-indicator">BASELINE IN PROGRESS</div>';
        testInfo.appendChild(testInProgress);
    }

    /**
     * Show data reset state
     */
    showDataReset() {
        if (!this.recentTestElement) return;
        
        const testInfo = this.recentTestElement.querySelector('.test-info');
        if (!testInfo) return;
        
        // Standard reset message
        testInfo.innerHTML = `
            <div class="contestant-name">DATA RESET</div>
            <div class="hat-type">Waiting for new measurements</div>
            <div class="attenuation">0.00 dB</div>
            <div class="test-date">All previous data cleared</div>
        `;
        
        // Remove any existing measurement indicators
        this.removeInProgressIndicator();
    }

    /**
     * Show first baseline measurement state
     */
    showFirstBaselineMeasurement() {
        if (!this.recentTestElement) return;
        
        const testInfo = this.recentTestElement.querySelector('.test-info');
        if (!testInfo) return;
        
        // Update UI to indicate new baseline test
        testInfo.innerHTML = `
            <div class="contestant-name">NEW BASELINE TEST</div>
            <div class="hat-type">Starting baseline measurement...</div>
            <div class="attenuation">0.00 dB</div>
            <div class="test-date">In Progress</div>
        `;
        
        // Add the "measurement in progress" indicator
        const testInProgress = document.createElement('div');
        testInProgress.className = 'test-in-progress';
        testInProgress.innerHTML = '<div class="measuring-indicator">NEW BASELINE IN PROGRESS</div>';
        testInfo.appendChild(testInProgress);
    }

    /**
     * Remove the "in progress" indicator
     */
    removeInProgressIndicator() {
        const testInProgress = document.querySelector('.test-in-progress');
        if (testInProgress) {
            testInProgress.remove();
        }
    }

    /**
     * Show a notification message overlay
     * @param {string} message - Message to display
     * @param {string} type - Type of notification ('error', 'success', 'warning', 'info')
     * @param {number} duration - Duration in milliseconds before automatically hiding
     */
    showNotification(message, type = 'info', duration = 5000) {
        // Remove any existing notifications
        const existingNotifications = document.querySelectorAll('.notification-overlay');
        existingNotifications.forEach(notification => notification.remove());
        
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification-overlay notification-${type}`;
        notification.textContent = message;
        
        // Style based on type
        let backgroundColor = '#333';
        let color = '#fff';
        let borderColor = '#555';
        
        switch (type) {
            case 'error':
                backgroundColor = 'rgba(255, 0, 0, 0.8)';
                borderColor = '#ff5500';
                break;
            case 'success':
                backgroundColor = 'rgba(0, 170, 0, 0.8)';
                borderColor = '#33ff33';
                break;
            case 'warning':
                backgroundColor = 'rgba(255, 165, 0, 0.8)';
                borderColor = '#ffcc00';
                break;
            case 'info':
            default:
                backgroundColor = 'rgba(0, 0, 0, 0.8)';
                borderColor = '#33ff33';
        }
        
        // Apply styles
        notification.style.position = 'fixed';
        notification.style.top = '50%';
        notification.style.left = '50%';
        notification.style.transform = 'translate(-50%, -50%)';
        notification.style.backgroundColor = backgroundColor;
        notification.style.color = color;
        notification.style.padding = '20px';
        notification.style.fontSize = '24px';
        notification.style.fontWeight = 'bold';
        notification.style.zIndex = '9999';
        notification.style.borderRadius = '10px';
        notification.style.border = `2px solid ${borderColor}`;
        notification.style.textAlign = 'center';
        
        // Add to DOM
        document.body.appendChild(notification);
        
        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, duration);
        }
        
        return notification;
    }

    /**
     * Show emergency reset notification
     */
    showEmergencyReset() {
        return this.showNotification('EMERGENCY RESET - NEW BASELINE TEST STARTED', 'error', 5000);
    }

    /**
     * Show reset notification in the recent test UI
     * @param {string} message - Message to display
     */
    showResetNotificationInUI(message = 'CHART DATA CLEARED FOR NEW TEST') {
        if (!this.recentTestElement) return;
        
        const testInfo = this.recentTestElement.querySelector('.test-info');
        if (!testInfo) return;
        
        const resetNotification = document.createElement('div');
        resetNotification.className = 'reset-notification';
        resetNotification.textContent = message;
        resetNotification.style.color = '#ff5500';
        resetNotification.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
        resetNotification.style.padding = '10px';
        resetNotification.style.margin = '10px 0';
        resetNotification.style.textAlign = 'center';
        resetNotification.style.fontWeight = 'bold';
        resetNotification.style.border = '2px solid #ff5500';
        resetNotification.style.borderRadius = '5px';
        testInfo.appendChild(resetNotification);
        
        // Remove the notification after 5 seconds
        setTimeout(() => {
            if (resetNotification && resetNotification.parentNode) {
                resetNotification.parentNode.removeChild(resetNotification);
            }
        }, 5000);
        
        return resetNotification;
    }
}

// Export the UIManager class
window.UIManager = UIManager; 