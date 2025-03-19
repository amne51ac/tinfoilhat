-- Schema for the Tinfoil Hat Competition Database

-- Drop tables if they exist
DROP TABLE IF EXISTS contestant;
DROP TABLE IF EXISTS test_result;
DROP TABLE IF EXISTS test_data;
DROP TABLE IF EXISTS measurement_cache;

-- Contestant table
CREATE TABLE contestant (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone_number TEXT,
  email TEXT,
  notes TEXT,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Test result table
CREATE TABLE test_result (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contestant_id INTEGER NOT NULL,
  test_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  average_attenuation REAL NOT NULL,
  is_best_score BOOLEAN NOT NULL DEFAULT 0,
  hat_type TEXT DEFAULT 'classic',
  FOREIGN KEY (contestant_id) REFERENCES contestant (id)
);

-- Test data table (stores individual frequency measurements)
CREATE TABLE test_data (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  test_result_id INTEGER NOT NULL,
  frequency INTEGER NOT NULL,
  baseline_level REAL NOT NULL,
  hat_level REAL NOT NULL,
  attenuation REAL NOT NULL,
  FOREIGN KEY (test_result_id) REFERENCES test_result (id)
);

-- Measurement cache table (for in-progress measurements persistence between app restarts)
CREATE TABLE measurement_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,   -- 'baseline' or 'hat'
  frequency INTEGER NOT NULL,
  power REAL NOT NULL,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(type, frequency)   -- Ensure only one measurement per type/frequency
); 