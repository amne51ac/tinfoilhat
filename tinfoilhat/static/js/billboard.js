/**
 * billboard.js
 * Main application script for the Tinfoil Hat Competition Billboard
 */

// Wait for DOM to be fully loaded before initializing
document.addEventListener('DOMContentLoaded', function() {
    // Initialize managers
    const chartManager = new ChartManager();
    const dataManager = new DataManager();
    const leaderboardManager = new LeaderboardManager();
    const uiManager = new UIManager();
    
    // Initialize the power chart
    const powerChartCanvas = document.getElementById('powerChart');
    if (powerChartCanvas) {
        chartManager.initializeChart(powerChartCanvas);
    }
    
    // Load frequency labels if available
    if (window.frequencyLabels && Object.keys(window.frequencyLabels).length > 0) {
        dataManager.setFrequencyLabels(window.frequencyLabels);
        chartManager.updateChartCallbacks(window.frequencyLabels);
    }
    
    // Initialize event handler with all managers
    const eventHandler = new EventHandler(chartManager, dataManager, leaderboardManager, uiManager);
    
    // Load initial spectrum data if available
    if (window.initialSpectrumData) {
        console.log("Found initial spectrum data:", window.initialSpectrumData);
        chartManager.updateChart(window.initialSpectrumData);
        dataManager.updateWithSpectrumData(window.initialSpectrumData);
    }
    
    // Set up Server-Sent Events with the last event ID
    const lastId = window.lastEventId || 0;
    eventHandler.setupSSE(lastId);
    
    // Auto reload page once per hour to keep things fresh
    setTimeout(() => {
        console.log("Auto-refreshing page after 1 hour");
        window.location.reload();
    }, 3600000); // 1 hour
}); 