-- Runs once, when the db volume is first created. Mirrors `scripts/db.sh init`.
CREATE ROLE cfv_owner LOGIN PASSWORD 'cfv_owner_dev';
CREATE ROLE cfv_app LOGIN PASSWORD 'cfv_app_dev';
CREATE ROLE cfv_readonly LOGIN PASSWORD 'cfv_read_dev';
COMMENT ON ROLE cfv_owner IS 'Owns every schema and runs migrations. Never used by the running app.';
COMMENT ON ROLE cfv_app IS 'What the API connects as. No DELETE anywhere on evidence; INSERT/SELECT only on the audit ledger.';
COMMENT ON ROLE cfv_readonly IS 'Read-only, for inspection in pgAdmin and for auditors.';
CREATE DATABASE case_file_vault OWNER cfv_owner ENCODING 'UTF8';
REVOKE ALL ON DATABASE case_file_vault FROM PUBLIC;
GRANT CONNECT ON DATABASE case_file_vault TO cfv_app, cfv_readonly;
\connect case_file_vault
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
