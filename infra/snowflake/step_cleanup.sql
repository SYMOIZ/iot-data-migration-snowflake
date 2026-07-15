-- ============================================================================
-- Project cleanup — MANUAL, run in Snowsight as ACCOUNTADMIN
-- Account: <SNOWFLAKE_ACCOUNT>
-- ============================================================================
-- Drops every Snowflake object created for this project: the database (and
-- everything inside it - schemas, tables, views, stages, pipes, streams,
-- tasks, file formats), the ingestion warehouse, and the three dedicated
-- service roles/users (Kafka connector, dbt, Streamlit dashboard).
--
-- This project never created a native "Streamlit App" object in Snowflake
-- (Snowflake's own Streamlit-in-Snowflake feature) - the dashboard is a
-- separately hosted Streamlit app on EC2 (see infra/streamlit/), which is
-- cleaned up on the AWS side, not here.
--
-- Nothing in this script touches any database/warehouse/role/user that
-- doesn't match the IOT_PLATFORM / IOT_INGEST_WH / *_ROLE / *_USER names
-- created for this project. If your account has other objects with similar
-- names that predate this project, verify before running.
--
-- Safe to run even if some objects were already removed (every statement
-- uses IF EXISTS).
-- ============================================================================

USE ROLE ACCOUNTADMIN;

-- ----------------------------------------------------------------------------
-- 1. Database - drops every schema/table/view/stage/pipe/stream/task/file
--    format inside it in one statement (BRONZE, BRONZE_BRONZE, BRONZE_SILVER,
--    BRONZE_GOLD, and anything else created under it).
-- ----------------------------------------------------------------------------
DROP DATABASE IF EXISTS IOT_PLATFORM CASCADE;

-- ----------------------------------------------------------------------------
-- 2. Warehouse
-- ----------------------------------------------------------------------------
DROP WAREHOUSE IF EXISTS IOT_INGEST_WH;

-- ----------------------------------------------------------------------------
-- 3. Service users (drop before roles)
-- ----------------------------------------------------------------------------
DROP USER IF EXISTS KAFKA_CONNECTOR_USER;
DROP USER IF EXISTS DBT_USER;
DROP USER IF EXISTS STREAMLIT_USER;

-- ----------------------------------------------------------------------------
-- 4. Service roles
-- ----------------------------------------------------------------------------
DROP ROLE IF EXISTS KAFKA_CONNECTOR_ROLE;
DROP ROLE IF EXISTS DBT_ROLE;
DROP ROLE IF EXISTS STREAMLIT_ROLE;

-- ----------------------------------------------------------------------------
-- Verification - all of these should return no rows / "does not exist"
-- ----------------------------------------------------------------------------
SHOW DATABASES LIKE 'IOT_PLATFORM';
SHOW WAREHOUSES LIKE 'IOT_INGEST_WH';
SHOW USERS LIKE 'KAFKA_CONNECTOR_USER';
SHOW USERS LIKE 'DBT_USER';
SHOW USERS LIKE 'STREAMLIT_USER';
SHOW ROLES LIKE 'KAFKA_CONNECTOR_ROLE';
SHOW ROLES LIKE 'DBT_ROLE';
SHOW ROLES LIKE 'STREAMLIT_ROLE';
