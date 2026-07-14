import pandas as pd
import streamlit as st

from ui import page_header, enable_autorefresh, connection_sidebar
from queries import (
    safe_load,
    get_latest_device_status,
    get_avg_temperature_by_device,
    get_avg_heart_rate_by_device,
    get_daily_telemetry_summary,
)

st.set_page_config(
    page_title="IoT Analytics Platform - Executive Overview",
    page_icon="📡",
    layout="wide",
)

enable_autorefresh(key="home_refresh")
page_header("Executive Overview")
connected = connection_sidebar()

if not connected:
    st.error(
        "Cannot reach Snowflake with the STREAMLIT_ROLE credentials configured "
        "for this app. Check `.streamlit/secrets.toml` and that the private "
        "key file exists on this host."
    )
    st.stop()

with st.spinner("Loading Gold layer data..."):
    status_df, status_err = safe_load(get_latest_device_status)
    temp_df, temp_err = safe_load(get_avg_temperature_by_device)
    hr_df, hr_err = safe_load(get_avg_heart_rate_by_device)
    daily_df, daily_err = safe_load(get_daily_telemetry_summary)

errors = [e for e in (status_err, temp_err, hr_err, daily_err) if e]
if errors:
    for e in errors:
        st.error(e)
    st.stop()

total_devices = status_df["DEVICE_ID"].nunique() if not status_df.empty else 0
total_records = int(daily_df["READING_COUNT"].sum()) if not daily_df.empty else 0

active_devices = 0
if not status_df.empty:
    cutoff = st.session_state.get("active_window_hours", 24)
    now_utc = status_df["LAST_SEEN_AT"].max()
    active_devices = status_df[
        status_df["LAST_SEEN_AT"] >= (now_utc - pd.Timedelta(hours=cutoff))
    ]["DEVICE_ID"].nunique()

avg_temp = temp_df["AVG_TEMPERATURE"].mean() if not temp_df.empty else None
avg_hr = hr_df["AVG_HEART_RATE"].mean() if not hr_df.empty else None
avg_battery = status_df["BATTERY"].mean() if not status_df.empty else None

col1, col2, col3 = st.columns(3)
col1.metric("Total Devices", f"{total_devices:,}")
col2.metric("Total Telemetry Records", f"{total_records:,}")
col3.metric("Active Devices (24h)", f"{active_devices:,}")

col4, col5, col6 = st.columns(3)
col4.metric("Average Temperature", f"{avg_temp:.1f} °C" if avg_temp is not None else "N/A")
col5.metric("Average Heart Rate", f"{avg_hr:.0f} bpm" if avg_hr is not None else "N/A")
col6.metric("Average Battery", f"{avg_battery:.0f}%" if avg_battery is not None else "N/A")

st.markdown("---")
st.subheader("Fleet Telemetry Volume (Daily)")
if daily_df.empty:
    st.info("No daily telemetry data yet.")
else:
    st.bar_chart(daily_df.set_index("EVENT_DATE")["READING_COUNT"], height=280)

st.subheader("Latest Device Snapshot")
st.dataframe(status_df, use_container_width=True, hide_index=True)

st.caption(
    "Use the sidebar to navigate to Device Health, Telemetry Analytics, "
    "Device Map, Operations, and the Raw Data Explorer."
)
