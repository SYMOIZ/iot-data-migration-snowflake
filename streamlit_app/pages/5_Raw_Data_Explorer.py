import streamlit as st

from ui import page_header, enable_autorefresh, connection_sidebar
from queries import safe_load, get_recent_cdc_events

st.set_page_config(page_title="Raw Data Explorer", page_icon="🔎", layout="wide")

enable_autorefresh(key="explorer_refresh")
page_header("Raw Data Explorer", "GOLD_RECENT_CDC_EVENTS")
connected = connection_sidebar()

if not connected:
    st.error("Not connected to Snowflake.")
    st.stop()

with st.spinner("Loading event data..."):
    events_df, err = safe_load(get_recent_cdc_events, limit=5000)

if err:
    st.error(err)
    st.stop()

if events_df.empty:
    st.info("No data available to explore yet.")
    st.stop()

st.subheader("Filters")
col1, col2 = st.columns([1, 2])

with col1:
    device_ids = sorted(events_df["DEVICE_ID"].dropna().unique().tolist())
    search_term = st.text_input("Search by Device ID (substring match)")
    selected_devices = st.multiselect("Or pick specific Device ID(s)", options=device_ids)

with col2:
    min_date = events_df["EVENT_TIMESTAMP"].min().date()
    max_date = events_df["EVENT_TIMESTAMP"].max().date()
    date_range = st.date_input(
        "Filter by Date",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

filtered = events_df.copy()

if search_term:
    filtered = filtered[filtered["DEVICE_ID"].str.contains(search_term, case=False, na=False)]

if selected_devices:
    filtered = filtered[filtered["DEVICE_ID"].isin(selected_devices)]

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    filtered = filtered[
        (filtered["EVENT_TIMESTAMP"].dt.date >= start_date)
        & (filtered["EVENT_TIMESTAMP"].dt.date <= end_date)
    ]

st.markdown("---")
st.subheader(f"Results ({len(filtered):,} rows)")
st.dataframe(filtered, use_container_width=True, hide_index=True)

csv_bytes = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label="⬇️ Export to CSV",
    data=csv_bytes,
    file_name="iot_gold_events_export.csv",
    mime="text/csv",
    disabled=filtered.empty,
)
