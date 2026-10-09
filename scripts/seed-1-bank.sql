-- =====================================================================
-- BuildrBank  ·  seed 1 of 2  ·  the bank
--
--   Supabase dashboard -> SQL Editor -> New query -> paste -> Run
--
-- Run scripts/schema.sql FIRST. This file only adds rows.
-- Safe to run more than once: every row has a primary key and the
-- inserts do nothing on conflict.
--
--   2 branches · 2 relationship managers · 3 customers
--   4 accounts · 8 transactions
-- =====================================================================
-- branches  (2 rows)
insert into branches (branch_id, name, address, city, tz, phone, extended_hours, active) values ('BR-COL-01', 'Colombo Fort Main', '28 Galle Face Terrace', 'Colombo', 'Asia/Colombo', '+94 11 234 5678', true, true) on conflict do nothing;
insert into branches (branch_id, name, address, city, tz, phone, extended_hours, active) values ('BR-KAN-01', 'Kandy Central', '12 Dalada Veediya', 'Kandy', 'Asia/Colombo', '+94 81 222 3344', true, true) on conflict do nothing;

-- relationship_managers  (2 rows)
insert into relationship_managers (rm_id, full_name, branch_id, email, phone, active) values ('RM-001', 'Dinesh Fernando', 'BR-COL-01', 'dinesh@buildrbank.lk', '+94 11 234 5680', true) on conflict do nothing;
insert into relationship_managers (rm_id, full_name, branch_id, email, phone, active) values ('RM-002', 'Sanduni Jayawardena', 'BR-KAN-01', 'sanduni@buildrbank.lk', '+94 81 222 3345', true) on conflict do nothing;

-- customers  (3 rows)
insert into customers (customer_id, full_name, email, phone, segment, risk_profile, kyc_status, active) values ('CUST-001', 'Isuru Alagiyawanna', 'isuru@example.com', '+94 77 123 4567', 'vip', 'moderate', 'verified', true) on conflict do nothing;
insert into customers (customer_id, full_name, email, phone, segment, risk_profile, kyc_status, active) values ('CUST-002', 'Nehara Silva', 'nehara@example.com', '+94 71 987 6543', 'retail', 'conservative', 'verified', true) on conflict do nothing;
insert into customers (customer_id, full_name, email, phone, segment, risk_profile, kyc_status, active) values ('CUST-004', 'Yasiru Perera', 'yasiru@example.com', '+94 76 555 1211', 'retail', 'moderate', 'verified', true) on conflict do nothing;

-- accounts  (4 rows)
insert into accounts (account_id, customer_id, account_type, balance, currency, opened_at, status) values ('ACC-100234', 'CUST-001', 'business_checking', 1250000.0, 'LKR', '2026-10-04T08:14:47.608288+00:00', 'active') on conflict do nothing;
insert into accounts (account_id, customer_id, account_type, balance, currency, opened_at, status) values ('ACC-100236', 'CUST-001', 'fixed_deposit', 500000.0, 'LKR', '2026-10-04T08:14:47.608288+00:00', 'active') on conflict do nothing;
insert into accounts (account_id, customer_id, account_type, balance, currency, opened_at, status) values ('ACC-100567', 'CUST-002', 'savings', 2340000.0, 'LKR', '2026-10-04T08:14:47.608288+00:00', 'active') on conflict do nothing;
insert into accounts (account_id, customer_id, account_type, balance, currency, opened_at, status) values ('ACC-100891', 'CUST-004', 'checking', 456000.0, 'LKR', '2026-10-04T08:14:47.608288+00:00', 'active') on conflict do nothing;

-- transactions  (8 rows)
insert into transactions (tx_id, account_id, tx_type, amount, currency, counterparty, status, reference, notes) values ('WIRE-30621', 'ACC-100234', 'wire_outgoing', 5000.0, 'USD', 'Nimal Perera / Sampath Bank', 'in_review', 'WIRE-30621', 'Held for compliance review - exceeds LKR 1M equivalent') on conflict do nothing;
insert into transactions (tx_id, account_id, tx_type, amount, currency, counterparty, status, reference, notes) values ('TXN-30619', 'ACC-100234', 'card_purchase', 12500.0, 'LKR', 'Cargills Food City', 'settled', 'TXN-30619', null) on conflict do nothing;
insert into transactions (tx_id, account_id, tx_type, amount, currency, counterparty, status, reference, notes) values ('SAL-30618', 'ACC-100234', 'salary_credit', 350000.0, 'LKR', 'BuildrLabs Ltd', 'settled', 'SAL-30618', null) on conflict do nothing;
insert into transactions (tx_id, account_id, tx_type, amount, currency, counterparty, status, reference, notes) values ('WIRE-30525', 'ACC-100234', 'wire_incoming', 2200.0, 'USD', 'Zuu Crew AI Consulting', 'settled', 'WIRE-30525', null) on conflict do nothing;
insert into transactions (tx_id, account_id, tx_type, amount, currency, counterparty, status, reference, notes) values ('WIRE-30702', 'ACC-100567', 'wire_incoming', 12000.0, 'USD', 'Overseas Tech Ltd', 'settled', 'WIRE-30702', null) on conflict do nothing;
insert into transactions (tx_id, account_id, tx_type, amount, currency, counterparty, status, reference, notes) values ('LOAN-30628', 'ACC-100567', 'loan_disbursement', 2000000.0, 'LKR', 'BuildrBank Personal Loan', 'settled', 'LOAN-30628', null) on conflict do nothing;
insert into transactions (tx_id, account_id, tx_type, amount, currency, counterparty, status, reference, notes) values ('SAL-30619', 'ACC-100891', 'salary_credit', 275000.0, 'LKR', 'Zuu Crew AI', 'settled', 'SAL-30619', null) on conflict do nothing;
insert into transactions (tx_id, account_id, tx_type, amount, currency, counterparty, status, reference, notes) values ('UTL-30701', 'ACC-100891', 'utility_payment', 4500.0, 'LKR', 'Water Board', 'settled', 'UTL-30701', null) on conflict do nothing;
