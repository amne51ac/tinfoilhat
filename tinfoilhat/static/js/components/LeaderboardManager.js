/**
 * LeaderboardManager.js
 * Handles leaderboard updates and display
 */

class LeaderboardManager {
    constructor(errorHandler) {
        // Store references to leaderboard tables
        this.leaderboardTables = {
            classic: document.getElementById('classic-leaderboard'),
            hybrid: document.getElementById('hybrid-leaderboard')
        };
        this.errorHandler = errorHandler;
        
        // Create safe versions of critical methods
        if (this.errorHandler) {
            this.updateLeaderboard = this.errorHandler.makeSafe(
                this, 'LeaderboardManager', 'updateLeaderboard', this.updateLeaderboard
            );
        }
    }

    /**
     * Update a leaderboard with new data
     * @param {string} type - Type of leaderboard ('classic' or 'hybrid')
     * @param {Array} data - Leaderboard data array
     */
    updateLeaderboard(type, data) {
        try {
            if (!data || !Array.isArray(data)) {
                if (this.errorHandler) {
                    this.errorHandler.handleError('LeaderboardManager', 'updateLeaderboard', 
                        `Invalid data for leaderboard type: ${type}`, 'warning');
                } else {
                    console.warn(`Invalid data for leaderboard type: ${type}`);
                }
                return;
            }
            
            if (!this.leaderboardTables[type]) {
                if (this.errorHandler) {
                    this.errorHandler.handleError('LeaderboardManager', 'updateLeaderboard', 
                        `Unknown leaderboard type: ${type}`, 'warning');
                } else {
                    console.warn(`Unknown leaderboard type: ${type}`);
                }
                return;
            }
    
            const tableBody = this.leaderboardTables[type].querySelector('tbody');
            if (!tableBody) {
                if (this.errorHandler) {
                    this.errorHandler.handleError('LeaderboardManager', 'updateLeaderboard', 
                        `Could not find tbody in ${type} leaderboard`, 'warning');
                } else {
                    console.warn(`Could not find tbody in ${type} leaderboard`);
                }
                return;
            }
    
            // Clear existing rows
            tableBody.innerHTML = '';
    
            // If no data, show empty message
            if (data.length === 0) {
                const emptyRow = document.createElement('tr');
                emptyRow.innerHTML = '<td colspan="3" class="text-center">No entries yet</td>';
                tableBody.appendChild(emptyRow);
                return;
            }
    
            // Add rows for each contestant
            data.forEach((entry, index) => {
                if (!entry || typeof entry !== 'object') {
                    if (this.errorHandler) {
                        this.errorHandler.handleError('LeaderboardManager', 'updateLeaderboard', 
                            `Invalid entry at index ${index}`, 'info');
                    }
                    return; // Skip this entry
                }
                
                const rank = index + 1;
                const row = document.createElement('tr');
                
                // Add special classes for top 3
                if (rank === 1) {
                    row.classList.add('first-place');
                } else if (rank === 2) {
                    row.classList.add('second-place');
                } else if (rank === 3) {
                    row.classList.add('third-place');
                }
                
                // Ensure we have valid attenuation value
                const attenuation = parseFloat(entry.attenuation || 0);
                
                // Add negative attenuation class if needed
                const attenuationClass = attenuation < 0 ? 'negative-attenuation' : '';
                
                const name = entry.name || 'Unknown';
                
                row.innerHTML = `
                    <td class="rank">${rank}</td>
                    <td>${name}</td>
                    <td class="attenuation ${attenuationClass}">
                        ${attenuation.toFixed(2)}
                    </td>
                `;
                
                tableBody.appendChild(row);
            });
        } catch (error) {
            if (this.errorHandler) {
                this.errorHandler.handleError('LeaderboardManager', 'updateLeaderboard', error);
            } else {
                console.error('Error updating leaderboard:', error);
            }
        }
    }

    /**
     * Get current leaderboard data
     * @param {string} type - Type of leaderboard ('classic' or 'hybrid')
     * @returns {Array} Array of leaderboard entries
     */
    getLeaderboardData(type) {
        try {
            if (!this.leaderboardTables[type]) {
                if (this.errorHandler) {
                    this.errorHandler.handleError('LeaderboardManager', 'getLeaderboardData', 
                        `Unknown leaderboard type: ${type}`, 'warning');
                }
                return [];
            }
            
            const tableBody = this.leaderboardTables[type].querySelector('tbody');
            if (!tableBody) {
                if (this.errorHandler) {
                    this.errorHandler.handleError('LeaderboardManager', 'getLeaderboardData', 
                        `Could not find tbody in ${type} leaderboard`, 'warning');
                }
                return [];
            }
            
            const rows = tableBody.querySelectorAll('tr');
            const entries = [];
            
            rows.forEach(row => {
                // Skip rows with colspan (empty message)
                if (row.querySelector('td[colspan]')) return;
                
                const name = row.cells[1].textContent.trim();
                const attenuation = parseFloat(row.cells[2].textContent.trim());
                
                if (name && !isNaN(attenuation)) {
                    entries.push({ name, attenuation });
                }
            });
            
            return entries;
        } catch (error) {
            if (this.errorHandler) {
                this.errorHandler.handleError('LeaderboardManager', 'getLeaderboardData', error);
            } else {
                console.error('Error getting leaderboard data:', error);
            }
            return [];
        }
    }
}

// Export the LeaderboardManager class
window.LeaderboardManager = LeaderboardManager; 