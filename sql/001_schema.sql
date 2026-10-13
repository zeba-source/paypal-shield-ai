USE fintech_db;

CREATE TABLE IF NOT EXISTS transactions (
    step INT NULL,
    type VARCHAR(30) NULL,
    amount DECIMAL(18,2) NULL,
    nameOrig VARCHAR(50) NULL,
    oldbalanceOrg DECIMAL(18,2) NULL,
    newbalanceOrig DECIMAL(18,2) NULL,
    nameDest VARCHAR(50) NULL,
    oldbalanceDest DECIMAL(18,2) NULL,
    newbalanceDest DECIMAL(18,2) NULL,
    isFraud TINYINT NULL,
    isFlaggedFraud TINYINT NULL,
    event_time DATETIME NULL,
    lat DOUBLE NULL,
    lon DOUBLE NULL,
    country VARCHAR(50) NULL,
    city VARCHAR(50) NULL
);

SET @txn_id_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND COLUMN_NAME = 'txn_id'
);

SET @id_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND COLUMN_NAME = 'id'
);

SET @txn_id_sql := IF(
    @txn_id_exists = 0 AND @id_exists = 0,
    'ALTER TABLE transactions ADD COLUMN txn_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST',
    'SELECT 1'
);

PREPARE txn_id_stmt FROM @txn_id_sql;
EXECUTE txn_id_stmt;
DEALLOCATE PREPARE txn_id_stmt;

SET @event_time_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND COLUMN_NAME = 'event_time'
);

SET @event_time_sql := IF(
    @event_time_exists = 0,
    'ALTER TABLE transactions ADD COLUMN event_time DATETIME NULL',
    'SELECT 1'
);

PREPARE event_time_stmt FROM @event_time_sql;
EXECUTE event_time_stmt;
DEALLOCATE PREPARE event_time_stmt;

SET @lat_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND COLUMN_NAME = 'lat'
);

SET @lat_sql := IF(
    @lat_exists = 0,
    'ALTER TABLE transactions ADD COLUMN lat DOUBLE NULL',
    'SELECT 1'
);

PREPARE lat_stmt FROM @lat_sql;
EXECUTE lat_stmt;
DEALLOCATE PREPARE lat_stmt;

SET @lon_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND COLUMN_NAME = 'lon'
);

SET @lon_sql := IF(
    @lon_exists = 0,
    'ALTER TABLE transactions ADD COLUMN lon DOUBLE NULL',
    'SELECT 1'
);

PREPARE lon_stmt FROM @lon_sql;
EXECUTE lon_stmt;
DEALLOCATE PREPARE lon_stmt;

SET @country_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND COLUMN_NAME = 'country'
);

SET @country_sql := IF(
    @country_exists = 0,
    'ALTER TABLE transactions ADD COLUMN country VARCHAR(50) NULL',
    'SELECT 1'
);

PREPARE country_stmt FROM @country_sql;
EXECUTE country_stmt;
DEALLOCATE PREPARE country_stmt;

SET @city_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND COLUMN_NAME = 'city'
);

SET @city_sql := IF(
    @city_exists = 0,
    'ALTER TABLE transactions ADD COLUMN city VARCHAR(50) NULL',
    'SELECT 1'
);

PREPARE city_stmt FROM @city_sql;
EXECUTE city_stmt;
DEALLOCATE PREPARE city_stmt;

SET @nameorig_idx_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND INDEX_NAME = 'idx_transactions_nameOrig_event_time'
);

SET @nameorig_idx_sql := IF(
    @nameorig_idx_exists = 0,
    'CREATE INDEX idx_transactions_nameOrig_event_time ON transactions (nameOrig, event_time)',
    'SELECT 1'
);

PREPARE idx_nameorig FROM @nameorig_idx_sql;
EXECUTE idx_nameorig;
DEALLOCATE PREPARE idx_nameorig;

SET @namedest_idx_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'transactions'
      AND INDEX_NAME = 'idx_transactions_nameDest_event_time'
);

SET @namedest_idx_sql := IF(
    @namedest_idx_exists = 0,
    'CREATE INDEX idx_transactions_nameDest_event_time ON transactions (nameDest, event_time)',
    'SELECT 1'
);

PREPARE idx_namedest FROM @namedest_idx_sql;
EXECUTE idx_namedest;
DEALLOCATE PREPARE idx_namedest;

CREATE TABLE IF NOT EXISTS account_profiles (
    account_id VARCHAR(50) NOT NULL,
    home_city VARCHAR(50) NULL,
    home_country VARCHAR(50) NULL,
    home_lat DOUBLE NULL,
    home_lon DOUBLE NULL,
    avg_amount DECIMAL(18,2) NULL,
    txn_count INT NULL,
    hour_histogram JSON NULL,
    last_txn_time DATETIME NULL,
    last_lat DOUBLE NULL,
    last_lon DOUBLE NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id)
);

CREATE TABLE IF NOT EXISTS risk_alerts (
    id BIGINT NOT NULL AUTO_INCREMENT,
    txn_id BIGINT NOT NULL,
    account_id VARCHAR(50) NULL,
    frequency_score DOUBLE NULL,
    time_score DOUBLE NULL,
    geo_score DOUBLE NULL,
    final_score DOUBLE NULL,
    action VARCHAR(50) NULL,
    reasons JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS verification_requests (
    id BIGINT NOT NULL AUTO_INCREMENT,
    txn_id BIGINT NOT NULL,
    account_id VARCHAR(50) NULL,
    otp_hash VARCHAR(255) NULL,
    status ENUM('PENDING', 'PASSED', 'FAILED', 'EXPIRED') DEFAULT 'PENDING',
    attempts INT DEFAULT 0,
    expires_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS txn_status (
    txn_id BIGINT NOT NULL,
    status ENUM('APPROVED', 'PENDING_2FA', 'HELD', 'BLOCKED') NOT NULL DEFAULT 'PENDING_2FA',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (txn_id)
);
