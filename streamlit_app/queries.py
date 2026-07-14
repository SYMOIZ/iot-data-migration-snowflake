"""All SQL against Snowflake lives here, and it only ever touches the Gold
schema (GOLD_*). Bronze and Silver are intentionally never queried by this
app - STREAMLIT_ROLE has no grants there anyway, so it's enforced twice
over.
"""

import pandas as pd
import streamlit as st

from connection import get_connection, ConnectionError

CACHE_TTL = 30  # seconds - matches the dashboard's auto-refresh interval


def run_query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        columns = [c[0] for c in cur.description]
        rows = cur.fetchall()
        return pd.DataFrame(rows, columns=columns)
    finally:
        cur.close()


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_latest_device_status() -> pd.DataFrame:
    return run_query("""
        SELECT DEVICE_ID, LAST_SEEN_AT, LATITUDE, LONGITUDE, TEMPERATURE,
               HUMIDITY, HEART_RATE, BATTERY, BATTERY_STATUS
        FROM GOLD_LATEST_DEVICE_STATUS
        ORDER BY LAST_SEEN_AT DESC
    """)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_avg_temperature_by_device() -> pd.DataFrame:
    return run_query("""
        SELECT DEVICE_ID, READING_COUNT, AVG_TEMPERATURE, MIN_TEMPERATURE, MAX_TEMPERATURE
        FROM GOLD_AVG_TEMPERATURE_BY_DEVICE
        ORDER BY DEVICE_ID
    """)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_avg_heart_rate_by_device() -> pd.DataFrame:
    return run_query("""
        SELECT DEVICE_ID, READING_COUNT, AVG_HEART_RATE, MIN_HEART_RATE, MAX_HEART_RATE
        FROM GOLD_AVG_HEART_RATE_BY_DEVICE
        ORDER BY DEVICE_ID
    """)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_battery_health_summary() -> pd.DataFrame:
    return run_query("""
        SELECT BATTERY_STATUS, DEVICE_COUNT, AVG_BATTERY
        FROM GOLD_BATTERY_HEALTH_SUMMARY
        ORDER BY BATTERY_STATUS
    """)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_daily_telemetry_summary() -> pd.DataFrame:
    return run_query("""
        SELECT EVENT_DATE, READING_COUNT, ACTIVE_DEVICE_COUNT,
               AVG_TEMPERATURE, AVG_HUMIDITY, AVG_HEART_RATE, AVG_BATTERY
        FROM GOLD_DAILY_TELEMETRY_SUMMARY
        ORDER BY EVENT_DATE
    """)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_recent_cdc_events(limit: int = 500) -> pd.DataFrame:
    return run_query(f"""
        SELECT EVENT_ID, DEVICE_ID, OPERATION, EVENT_TIMESTAMP, TEMPERATURE,
               HUMIDITY, HEART_RATE, BATTERY, KAFKA_OFFSET, KAFKA_CREATE_TIME
        FROM GOLD_RECENT_CDC_EVENTS
        ORDER BY KAFKA_OFFSET DESC
        LIMIT {int(limit)}
    """)


def safe_load(loader, *args, **kwargs):
    """Run a Gold query, returning (dataframe_or_None, error_message_or_None)."""
    try:
        return loader(*args, **kwargs), None
    except ConnectionError as exc:
        return None, str(exc)
    except Exception as exc:
        return None, f"Query failed: {exc}"
