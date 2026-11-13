-- ==============================================================================
-- Bank Information Query Agent - Database Schema (3 related tables)
--   bank_information 1 ── * user_accounts 1 ── * transactions
-- Rebuild everything with: python -m database.build_db
-- ==============================================================================

DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS user_accounts CASCADE;
DROP TABLE IF EXISTS bank_information CASCADE;

-- Table 1: bank branches
CREATE TABLE bank_information (
    bank_id SERIAL PRIMARY KEY,
    bank_name VARCHAR(150) NOT NULL,
    routing_number VARCHAR(20) NOT NULL UNIQUE,
    swift_code VARCHAR(20) NOT NULL,
    district VARCHAR(50) NOT NULL,
    address TEXT NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE'))
);

-- Table 2: customer accounts (each belongs to one branch)
CREATE TABLE user_accounts (
    account_id SERIAL PRIMARY KEY,
    user_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    account_number VARCHAR(30) NOT NULL UNIQUE,
    bank_id INT NOT NULL REFERENCES bank_information(bank_id) ON DELETE CASCADE,
    account_type VARCHAR(30) NOT NULL DEFAULT 'SAVINGS'
        CHECK (account_type IN ('SAVINGS', 'CURRENT', 'SALARY', 'FIXED_DEPOSIT')),
    balance NUMERIC(15, 2) NOT NULL DEFAULT 0.00 CHECK (balance >= 0),
    created_at DATE
);

-- Table 3: deposits and withdrawals (biggest table; each belongs to one account)
CREATE TABLE transactions (
    txn_id SERIAL PRIMARY KEY,
    account_id INT NOT NULL REFERENCES user_accounts(account_id) ON DELETE CASCADE,
    txn_date DATE NOT NULL,
    txn_type VARCHAR(20) NOT NULL CHECK (txn_type IN ('DEPOSIT', 'WITHDRAWAL')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0)
);

CREATE INDEX idx_bank_district ON bank_information (district);
CREATE INDEX idx_bank_name ON bank_information (bank_name);
CREATE INDEX idx_bank_status ON bank_information (status);
CREATE INDEX idx_user_bank_id ON user_accounts (bank_id);
CREATE INDEX idx_txn_account ON transactions (account_id);
CREATE INDEX idx_txn_date ON transactions (txn_date);
