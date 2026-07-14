import datetime as dt

import pandas as pd
import streamlit as st

from ui import page_header, enable_autorefresh, connection_sidebar
from queries import safe_load, get_recent_cdc_events, get_latest_device_status

st.set_page_config(page_title="Operations", page_icon="⚙️", layout="wide")

enable_autorefresh(key="ops_refresh")
page_header("Operations")
connected = connection_sidebar()

if not connected:
    st.error("Not connected to Snowflake.")
    st.stop()

with st.spinner("Loading pipeline operations data..."):
    events_df, events_err = safe_load(get_recent_cdc_events, limit=25)
    status_df, status_err = safe_load(get_latest_device_status)

for e in (events_err, status_err):
    if e:
        st.error(e)
if events_err or status_err:
    st.stop()

op_labels = {"c": "🟢 Insert", "r": "🔵 Snapshot", "u": "🟡 Update", "d": "🔴 Delete"}

last_arrival = status_df["LAST_SEEN_AT"].max() if not status_df.empty else None

col1, col2, col3 = st.columns(3)
col1.metric("Last Data Arrival", last_arrival.strftime("%Y-%m-%d %H:%M:%S") if last_arrival is not None else "N/A")

if last_arrival is not None:
    elapsed = dt.datetime.now(tz=last_arrival.tzinfo) - last_arrival if last_arrival.tzinfo else dt.datetime.utcnow() - last_arrival
    elapsed_minutes = elapsed.total_seconds() / 60
    if elapsed_minutes < 5:
        health, css = "Healthy", "🟢"
    elif elapsed_minutes < 30:
        health, css = "Degraded", "🟡"
    else:
        health, css = "Down", "🔴"
    col2.metric("Pipeline Health Status", f"{css} {health}")
    col3.metric("Minutes Since Last Data", f"{elapsed_minutes:.1f}")
else:
    col2.metric("Pipeline Health Status", "🔴 Unknown")
    col3.metric("Minutes Since Last Data", "N/A")

st.markdown("---")
st.subheader("Latest CDC Events")
if events_df.empty:
    st.info("No CDC events recorded yet.")
else:
    display_df = events_df.copy()
    display_df["OPERATION"] = display_df["OPERATION"].map(lambda op: op_labels.get(op, op))
    st.dataframe(
        display_df[["EVENT_ID", "DEVICE_ID", "OPERATION", "EVENT_TIMESTAMP", "TEMPERATURE", "HEART_RATE", "BATTERY"]],
        use_container_width=True,
        hide_index=True,
    )

st.caption(
    "Sourced from `GOLD_RECENT_CDC_EVENTS` - the only Gold model exposed at "
    "individual-event granularity, added specifically so this Operations "
    "view doesn't need to query Bronze or Silver directly."
)
