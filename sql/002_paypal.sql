CREATE TABLE IF NOT EXISTS `paypal_orders` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `txn_id` BIGINT NULL,
    `paypal_order_id` VARCHAR(64) NOT NULL,
    `authorization_id` VARCHAR(64) NULL,
    `capture_id` VARCHAR(64) NULL,
    `payer_id` VARCHAR(64) NULL,
    `payer_email_masked` VARCHAR(100) NULL,
    `payer_country` CHAR(2) NULL,
    `shipping_country` CHAR(2) NULL,
    `amount` DECIMAL(12,2) NOT NULL,
    `currency` CHAR(3) NOT NULL,
    `payment_status` ENUM('CREATED','AUTHORIZED','PENDING_2FA','PENDING_REVIEW','CAPTURED','VOIDED','FAILED') NOT NULL DEFAULT 'CREATED',
    `client_ip_hash` VARCHAR(64) NULL,
    `device_hash` VARCHAR(64) NULL,
    `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_paypal_orders_order_id` (`paypal_order_id`),
    INDEX `idx_paypal_orders_payer_id` (`payer_id`),
    INDEX `idx_paypal_orders_payment_status` (`payment_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `txn_events`
    MODIFY COLUMN `stage` ENUM(
        'RECEIVED','AGENTS_SCORED','POLICY_DECISION','2FA_SENT','2FA_VERIFIED','2FA_FAILED','2FA_EXPIRED',
        'APPROVED','HELD','BLOCKED','ANALYST_REVIEW',
        'PAYPAL_ORDER_CREATED','PAYPAL_AUTHORIZED','PAYPAL_CAPTURED','PAYPAL_VOIDED','PAYPAL_CAPTURE_FAILED'
    ) NOT NULL;