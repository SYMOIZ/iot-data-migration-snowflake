import pandas as pd
import streamlit as st

from ui import page_header, enable_autorefresh, connection_sidebar
from queries import safe_load, get_latest_device_status, get_battery_health_summary

st.set_page_config(page_title="Device Health", page_icon="🩺", layout="wide")

enable_autorefresh(key="health_refresh")
page_header("Device Health")
connected = connection_sidebar()

if not connected:
    st.error("Not connected to Snowflake.")
    st.stop()

with st.spinner("Loading device health data..."):
    status_df, status_err = safe_load(get_latest_device_status)
    battery_df, battery_err = safe_load(get_battery_health_summary)

for e in (status_err, battery_err):
    if e:
        st.error(e)
if status_err or battery_err:
    st.stop()

offline_threshold_hours = st.sidebar.slider(
    "Offline threshold (hours since last reading)", min_value=1, max_value=72, value=6
)

st.subheader("Latest Device Status")
st.dataframe(
    status_df.style.map(
        lambda v: "background-color: #FEE2E2" if v == "low"
        else ("background-color: #FEF9C3" if v == "medium" else "background-color: #DCFCE7"),
        subset=["BATTERY_STATUS"],
    ) if not status_df.empty else status_df,
    use_container_width=True,
    hide_index=True,
)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Battery Health")
    if battery_df.empty:
        st.info("No battery health data yet.")
    else:
        st.bar_chart(battery_df.set_index("BATTERY_STATUS")["DEVICE_COUNT"], height=280)
        st.dataframe(battery_df, use_container_width=True, hide_index=True)

with col2:
    st.subheader("Offline Devices")
    if status_df.empty:
        st.info("No device data yet.")
    else:
        now_utc = status_df["LAST_SEEN_AT"].max()
        offline_df = status_df[
            status_df["LAST_SEEN_AT"] < (now_utc - pd.Timedelta(hours=offline_threshold_hours))
        ]
        st.metric("Offline Devices", len(offline_df))
        if offline_df.empty:
            st.success(f"All devices reported within the last {offline_threshold_hours}h.")
        else:
            st.dataframe(
                offline_df[["DEVICE_ID", "LAST_SEEN_AT", "BATTERY_STATUS"]],
                use_container_width=True,
                hide_index=True,
            )
