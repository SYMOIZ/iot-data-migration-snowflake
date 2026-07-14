import streamlit as st

from ui import page_header, enable_autorefresh, connection_sidebar
from queries import safe_load, get_daily_telemetry_summary, get_avg_temperature_by_device, get_avg_heart_rate_by_device

st.set_page_config(page_title="Telemetry Analytics", page_icon="📈", layout="wide")

enable_autorefresh(key="telemetry_refresh")
page_header("Telemetry Analytics")
connected = connection_sidebar()

if not connected:
    st.error("Not connected to Snowflake.")
    st.stop()

with st.spinner("Loading telemetry analytics..."):
    daily_df, daily_err = safe_load(get_daily_telemetry_summary)
    temp_df, temp_err = safe_load(get_avg_temperature_by_device)
    hr_df, hr_err = safe_load(get_avg_heart_rate_by_device)

for e in (daily_err, temp_err, hr_err):
    if e:
        st.error(e)
if daily_err or temp_err or hr_err:
    st.stop()

if daily_df.empty:
    st.info("No telemetry data yet - GOLD_DAILY_TELEMETRY_SUMMARY is empty.")
    st.stop()

daily_indexed = daily_df.set_index("EVENT_DATE")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Temperature Trend (Fleet Daily Avg)")
    st.line_chart(daily_indexed["AVG_TEMPERATURE"], height=280)
with col2:
    st.subheader("Heart Rate Trend (Fleet Daily Avg)")
    st.line_chart(daily_indexed["AVG_HEART_RATE"], height=280)

col3, col4 = st.columns(2)
with col3:
    st.subheader("Humidity Trend (Fleet Daily Avg)")
    st.line_chart(daily_indexed["AVG_HUMIDITY"], height=280)
with col4:
    st.subheader("Daily Telemetry Volume")
    st.bar_chart(daily_indexed["READING_COUNT"], height=280)

st.markdown("---")
st.subheader("Per-Device Breakdown")
tab1, tab2 = st.tabs(["Temperature by Device", "Heart Rate by Device"])
with tab1:
    st.dataframe(temp_df, use_container_width=True, hide_index=True)
with tab2:
    st.dataframe(hr_df, use_container_width=True, hide_index=True)
