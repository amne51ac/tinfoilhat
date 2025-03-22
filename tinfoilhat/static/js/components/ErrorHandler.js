/**
 * ErrorHandler.js
 * Centralizes error handling for all frontend components
 */

class ErrorHandler {
    constructor() {
        this.errorCount = 0;
        this.errorLog = [];
        this.MAX_LOG_SIZE = 50;
        this.errorCallbacks = [];
    }

    /**
     * Register a callback function to be executed when an error occurs
     * @param {Function} callback - Function to call when an error occurs
     */
    registerErrorCallback(callback) {
        if (typeof callback === 'function' && !this.errorCallbacks.includes(callback)) {
            this.errorCallbacks.push(callback);
        }
    }

    /**
     * Handle and log an error
     * @param {string} component - The component where the error occurred
     * @param {string} method - The method where the error occurred
     * @param {Error|string} error - The error object or message
     * @param {string} severity - Error severity: 'error', 'warning', or 'info'
     * @returns {number} The error ID
     */
    handleError(component, method, error, severity = 'error') {
        const timestamp = new Date();
        const errorMessage = error instanceof Error ? error.message : error;
        const errorStack = error instanceof Error ? error.stack : null;
        
        // Create error object
        const errorObject = {
            id: ++this.errorCount,
            timestamp,
            component,
            method,
            message: errorMessage,
            stack: errorStack,
            severity
        };
        
        // Log to console based on severity
        if (severity === 'error') {
            console.error(`[${component}.${method}] ${errorMessage}`, errorStack ? errorStack : '');
        } else if (severity === 'warning') {
            console.warn(`[${component}.${method}] ${errorMessage}`);
        } else {
            console.info(`[${component}.${method}] ${errorMessage}`);
        }
        
        // Add to error log, maintaining max size
        this.errorLog.unshift(errorObject);
        if (this.errorLog.length > this.MAX_LOG_SIZE) {
            this.errorLog.pop();
        }
        
        // Execute registered callbacks
        this.errorCallbacks.forEach(callback => {
            try {
                callback(errorObject);
            } catch (cbError) {
                console.error('Error in error callback:', cbError);
            }
        });
        
        return errorObject.id;
    }

    /**
     * Create a safe version of a function that catches and handles errors
     * @param {Object} component - The component instance
     * @param {string} componentName - The component name
     * @param {string} methodName - The method name
     * @param {Function} fn - The function to make safe
     * @returns {Function} A safe version of the function
     */
    makeSafe(component, componentName, methodName, fn) {
        return (...args) => {
            try {
                return fn.apply(component, args);
            } catch (error) {
                this.handleError(componentName, methodName, error);
                return null;
            }
        };
    }

    /**
     * Create a safe version of a Promise-returning function that catches and handles errors
     * @param {Object} component - The component instance 
     * @param {string} componentName - The component name
     * @param {string} methodName - The method name
     * @param {Function} fn - The function that returns a Promise
     * @returns {Function} A safe version of the Promise-returning function
     */
    makeSafeAsync(component, componentName, methodName, fn) {
        return (...args) => {
            try {
                const result = fn.apply(component, args);
                if (result instanceof Promise) {
                    return result.catch(error => {
                        this.handleError(componentName, methodName, error);
                        throw error; // Rethrow to allow Promise chaining
                    });
                }
                return result;
            } catch (error) {
                this.handleError(componentName, methodName, error);
                return Promise.reject(error);
            }
        };
    }

    /**
     * Get the error log
     * @returns {Array} Array of error objects
     */
    getErrorLog() {
        return [...this.errorLog];
    }

    /**
     * Clear the error log
     */
    clearErrorLog() {
        this.errorLog = [];
    }
}

// Export the ErrorHandler class
window.ErrorHandler = ErrorHandler; 