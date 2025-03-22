/**
 * ChartManager.js
 * Handles chart initialization, updates, and configuration
 */

class ChartManager {
    constructor() {
        this.powerChart = null;
        this.chartInitialized = false;
    }

    /**
     * Initialize the power chart
     * @param {HTMLCanvasElement} canvasElement - The canvas element
     * @returns {Chart} - The chart instance
     */
    initializeChart(canvasElement) {
        const ctx = canvasElement.getContext('2d');
        
        // Initialize with empty data initially
        this.powerChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Baseline (dBm)',
                        data: [],
                        borderColor: 'rgba(51, 255, 51, 0.8)',
                        backgroundColor: 'rgba(51, 255, 51, 0.1)',
                        tension: 0.2,
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 0,
                        yAxisID: 'y'
                    }, 
                    {
                        label: 'With Hat (dBm)',
                        data: [],
                        borderColor: 'rgba(0, 200, 255, 0.8)',
                        backgroundColor: 'rgba(0, 200, 255, 0.1)',
                        tension: 0.2,
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 0,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Attenuation (dB)',
                        data: [],
                        borderColor: 'rgba(255, 204, 0, 0.8)',
                        backgroundColor: 'rgba(255, 204, 0, 0.1)',
                        tension: 0.2,
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 0,
                        yAxisID: 'attenuation'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'RF SPECTRUM ANALYSIS',
                        color: '#33ff33',
                        font: {
                            size: 18,
                            family: "'Press Start 2P', cursive",
                            weight: 'bold'
                        },
                        padding: {
                            top: 10,
                            bottom: 20
                        }
                    },
                    legend: {
                        labels: {
                            color: '#33ff33',
                            font: {
                                family: "'VT323', monospace",
                                size: 18
                            },
                            boxWidth: 15,
                            padding: 15
                        }
                    },
                    tooltip: {
                        titleFont: {
                            family: "'VT323', monospace",
                            size: 18
                        },
                        bodyFont: {
                            family: "'VT323', monospace",
                            size: 17
                        },
                        backgroundColor: 'rgba(0, 0, 0, 0.85)',
                        borderColor: '#33ff33',
                        borderWidth: 1,
                        padding: 12,
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.datasetIndex === 2) {
                                    // Attenuation dataset
                                    const value = context.parsed.y;
                                    const colorCode = value < 0 ? '🔴' : '🟢'; // Red for negative, green for positive
                                    return `${label}${value.toFixed(2)} dB ${colorCode}`;
                                } else {
                                    return `${label}${context.parsed.y.toFixed(2)} dBm`;
                                }
                            },
                            title: function(tooltipItems) {
                                const freq = tooltipItems[0].label;
                                if (freq) {
                                    return `${freq} MHz`;
                                }
                                return '';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'FREQUENCY (MHz)',
                            color: '#33ff33',
                            font: {
                                family: "'VT323', monospace",
                                size: 18
                            },
                            padding: {
                                top: 10
                            }
                        },
                        ticks: {
                            color: '#33ff33',
                            font: {
                                family: "'VT323', monospace",
                                size: 16
                            },
                            maxRotation: 45,
                            minRotation: 45,
                            callback: function(value, index, values) {
                                const freq = this.chart.data.labels[index];
                                if (!freq) return '';
                                
                                // Default case, just return the frequency
                                return freq;
                            }
                        },
                        grid: {
                            color: 'rgba(51, 255, 51, 0.08)',
                            tickBorderDash: [4, 4]
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'SIGNAL LEVEL (dBm)',
                            color: '#33ff33',
                            font: {
                                family: "'VT323', monospace",
                                size: 18
                            },
                            padding: {
                                bottom: 10
                            }
                        },
                        ticks: {
                            color: '#33ff33',
                            font: {
                                family: "'VT323', monospace",
                                size: 16
                            }
                        },
                        grid: {
                            color: 'rgba(51, 255, 51, 0.08)',
                            tickBorderDash: [4, 4]
                        },
                        min: -100,
                        max: -60
                    },
                    attenuation: {
                        position: 'right',
                        title: {
                            display: true,
                            text: 'ATTENUATION (dB)',
                            color: '#ffcc00',
                            font: {
                                family: "'VT323', monospace",
                                size: 18
                            },
                            padding: {
                                bottom: 10
                            }
                        },
                        ticks: {
                            color: '#ffcc00',
                            font: {
                                family: "'VT323', monospace",
                                size: 16
                            }
                        },
                        grid: {
                            drawOnChartArea: false,
                            color: 'rgba(255, 204, 0, 0.08)',
                            tickBorderDash: [4, 4]
                        },
                        min: -10,
                        max: 10
                    }
                }
            }
        });
        
        this.chartInitialized = true;
        return this.powerChart;
    }

    /**
     * Update chart callbacks to use frequency labels
     * @param {Object} frequencyLabels - Labels for frequencies
     */
    updateChartCallbacks(frequencyLabels = {}) {
        if (!this.chartInitialized || !this.powerChart) return;
        
        // Update tooltip callback to use frequencyLabels
        this.powerChart.options.plugins.tooltip.callbacks.title = function(tooltipItems) {
            const freq = tooltipItems[0].label;
            if (freq) {
                const freqNum = parseFloat(freq);
                // Check if we have frequencyLabels and use them
                if (frequencyLabels && Object.keys(frequencyLabels).length > 0) {
                    for (const [freqMhz, labelData] of Object.entries(frequencyLabels)) {
                        if (Math.abs(freqNum - parseFloat(freqMhz)) < 0.1) {
                            if (labelData[1]) {
                                return `${freq} MHz (${labelData[0]}) - ${labelData[1]}`;
                            } else {
                                return `${freq} MHz (${labelData[0]})`;
                            }
                        }
                    }
                }
                // If no matching label found or no labels available, just show frequency
                return `${freq} MHz`;
            }
            return '';
        };
        
        // Update x-axis tick callback to use frequencyLabels
        this.powerChart.options.scales.x.ticks.callback = function(value, index, values) {
            const freq = this.chart.data.labels[index];
            if (!freq) return '';
            
            // Make sure freq is a string
            const freqStr = freq.toString();
            
            // Try to get a label for this frequency
            const freqNum = parseFloat(freqStr);
            if (frequencyLabels && Object.keys(frequencyLabels).length > 0) {
                for (const [freqMhz, labelData] of Object.entries(frequencyLabels)) {
                    if (Math.abs(freqNum - parseFloat(freqMhz)) < 0.1) {
                        return `${freqStr} (${labelData[0]})`;
                    }
                }
            }
            
            // If no label found, use a common band name based on frequency if possible
            if (freqNum >= 88 && freqNum <= 108) return `${freqStr} (FM)`;
            if (freqNum >= 470 && freqNum <= 806) return `${freqStr} (UHF)`;
            if (freqNum >= 2400 && freqNum <= 2500) return `${freqStr} (WiFi)`;
            if (freqNum >= 5100 && freqNum <= 5800) return `${freqStr} (5G WiFi)`;
            
            // Default case, just return the frequency
            return freqStr;
        };
        
        this.powerChart.update();
    }

    /**
     * Update chart with spectrum data
     * @param {Object} spectrumData - Spectrum data with frequencies, baseline levels, hat levels, and attenuations
     */
    updateChart(spectrumData) {
        if (!this.chartInitialized || !this.powerChart) return;
        
        if (!spectrumData.frequencies || spectrumData.frequencies.length === 0) {
            console.warn("Missing frequencies in spectrum data");
            return;
        }
        
        // Format frequencies to 1 decimal place
        const formattedLabels = spectrumData.frequencies.map(f => {
            const fNum = typeof f === 'string' ? parseFloat(f) : f;
            return fNum.toFixed(1);
        });
        
        // Update chart data
        this.powerChart.data.labels = formattedLabels;
        this.powerChart.data.datasets[0].data = spectrumData.baseline_levels || [];
        this.powerChart.data.datasets[1].data = spectrumData.hat_levels || [];
        this.powerChart.data.datasets[2].data = spectrumData.attenuations || [];
        this.powerChart.update();
    }

    /**
     * Reset the chart to empty state
     */
    resetChart() {
        if (!this.chartInitialized || !this.powerChart) return;
        
        this.powerChart.data.labels = [];
        this.powerChart.data.datasets[0].data = [];
        this.powerChart.data.datasets[1].data = [];
        this.powerChart.data.datasets[2].data = [];
        this.powerChart.update();
    }

    /**
     * Update chart with live measurement data
     * @param {Array} frequencies - Array of frequencies
     * @param {Array} baselineLevels - Array of baseline power levels
     * @param {Array} hatLevels - Array of hat power levels
     * @param {Array} attenuations - Array of attenuation values
     */
    updateWithLiveData(frequencies, baselineLevels, hatLevels, attenuations) {
        if (!this.chartInitialized || !this.powerChart) return;
        
        // Don't update if no data available
        if (!frequencies || frequencies.length === 0) return;
        
        // Update power chart with available data
        const formattedLabels = frequencies.map(f => f.toFixed(1));
        this.powerChart.data.labels = formattedLabels;
        this.powerChart.data.datasets[0].data = baselineLevels;
        this.powerChart.data.datasets[1].data = hatLevels;
        this.powerChart.data.datasets[2].data = attenuations;
        this.powerChart.update();
    }
}

// Export the ChartManager class
window.ChartManager = ChartManager; 