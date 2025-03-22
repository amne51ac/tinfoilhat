/**
 * LeaderboardManager.js
 * Handles leaderboard updates and display
 */

class LeaderboardManager {
    constructor() {
        // Store references to leaderboard tables
        this.leaderboardTables = {
            classic: document.getElementById('classic-leaderboard'),
            hybrid: document.getElementById('hybrid-leaderboard')
        };
    }

    /**
     * Update a leaderboard with new data
     * @param {string} type - Type of leaderboard ('classic' or 'hybrid')
     * @param {Array} data - Leaderboard data array
     */
    updateLeaderboard(type, data) {
        if (!data || !Array.isArray(data) || !this.leaderboardTables[type]) {
            console.warn(`Invalid data or unknown leaderboard type: ${type}`);
            return;
        }

        const tableBody = this.leaderboardTables[type].querySelector('tbody');
        if (!tableBody) {
            console.warn(`Could not find tbody in ${type} leaderboard`);
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
            
            // Add negative attenuation class if needed
            const attenuationClass = entry.attenuation < 0 ? 'negative-attenuation' : '';
            
            row.innerHTML = `
                <td class="rank">${rank}</td>
                <td>${entry.name}</td>
                <td class="attenuation ${attenuationClass}">
                    ${parseFloat(entry.attenuation).toFixed(2)}
                </td>
            `;
            
            tableBody.appendChild(row);
        });
    }

    /**
     * Get current leaderboard data
     * @param {string} type - Type of leaderboard ('classic' or 'hybrid')
     * @returns {Array} Array of leaderboard entries
     */
    getLeaderboardData(type) {
        if (!this.leaderboardTables[type]) return [];
        
        const tableBody = this.leaderboardTables[type].querySelector('tbody');
        if (!tableBody) return [];
        
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
    }
}

// Export the LeaderboardManager class
window.LeaderboardManager = LeaderboardManager; 