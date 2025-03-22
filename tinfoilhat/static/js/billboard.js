/**
 * billboard.js
 * Main application script for the Tinfoil Hat Competition Billboard
 */

// Wait for DOM to be fully loaded before initializing
document.addEventListener('DOMContentLoaded', function() {
    // Initialize error handler first
    const errorHandler = new ErrorHandler();
    
    // Create error notification callback
    errorHandler.registerErrorCallback(error => {
        if (error.severity === 'error') {
            // Only show UI notifications for serious errors
            const uiManager = window.uiManagerInstance;
            if (uiManager) {
                uiManager.showNotification(
                    `Error in ${error.component}: ${error.message}`,
                    'error',
                    10000
                );
            }
        }
    });
    
    // Initialize managers with error handler
    const chartManager = new ChartManager(errorHandler);
    const dataManager = new DataManager(errorHandler);
    const leaderboardManager = new LeaderboardManager(errorHandler);
    const uiManager = new UIManager(errorHandler);
    
    // Store UI manager globally for error callbacks to access
    window.uiManagerInstance = uiManager;
    
    // Initialize the power chart
    const powerChartCanvas = document.getElementById('powerChart');
    if (powerChartCanvas) {
        try {
            chartManager.initializeChart(powerChartCanvas);
        } catch (error) {
            errorHandler.handleError('billboard', 'initializeChart', error);
            uiManager.showNotification('Failed to initialize chart. Please reload the page.', 'error');
        }
    } else {
        errorHandler.handleError('billboard', 'DOMContentLoaded', 'Power chart canvas not found', 'warning');
    }
    
    // Load frequency labels if available
    if (window.frequencyLabels && Object.keys(window.frequencyLabels).length > 0) {
        try {
            dataManager.setFrequencyLabels(window.frequencyLabels);
            chartManager.updateChartCallbacks(window.frequencyLabels);
        } catch (error) {
            errorHandler.handleError('billboard', 'loadFrequencyLabels', error);
        }
    }
    
    // Initialize event handler with all managers
    const eventHandler = new EventHandler(chartManager, dataManager, leaderboardManager, uiManager, errorHandler);
    
    // Load initial spectrum data if available
    if (window.initialSpectrumData) {
        try {
            console.log("Found initial spectrum data:", window.initialSpectrumData);
            chartManager.updateChart(window.initialSpectrumData);
            dataManager.updateWithSpectrumData(window.initialSpectrumData);
        } catch (error) {
            errorHandler.handleError('billboard', 'loadInitialSpectrumData', error);
        }
    }
    
    // Set up Server-Sent Events with the last event ID
    const lastId = window.lastEventId || 0;
    try {
        eventHandler.setupSSE(lastId);
    } catch (error) {
        errorHandler.handleError('billboard', 'setupSSE', error);
        uiManager.showNotification('Failed to connect to event stream. Please reload the page.', 'error');
    }
    
    // Add global error handler for uncaught exceptions
    window.addEventListener('error', function(event) {
        errorHandler.handleError('window', 'globalError', event.error || event.message);
        return false;
    });
    
    // Add unhandled promise rejection handler
    window.addEventListener('unhandledrejection', function(event) {
        errorHandler.handleError('window', 'unhandledRejection', event.reason || 'Unhandled Promise rejection');
        return false;
    });
    
    // Auto reload page once per hour to keep things fresh
    setTimeout(() => {
        console.log("Auto-refreshing page after 1 hour");
        window.location.reload();
    }, 3600000); // 1 hour
}); 