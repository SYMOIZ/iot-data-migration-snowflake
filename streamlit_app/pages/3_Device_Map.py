import pydeck as pdk
import streamlit as st

from ui import page_header, enable_autorefresh, connection_sidebar
from queries import safe_load, get_latest_device_status

st.set_page_config(page_title="Device Map", page_icon="🗺️", layout="wide")

enable_autorefresh(key="map_refresh")
page_header("Device Map")
connected = connection_sidebar()

if not connected:
    st.error("Not connected to Snowflake.")
    st.stop()

with st.spinner("Loading device locations..."):
    status_df, err = safe_load(get_latest_device_status)

if err:
    st.error(err)
    st.stop()

geo_df = status_df.dropna(subset=["LATITUDE", "LONGITUDE"]).copy()

if geo_df.empty:
    st.info("No device location data available yet.")
    st.stop()

color_map = {
    "low": [220, 38, 38],
    "medium": [234, 179, 8],
    "ok": [22, 163, 74],
}
geo_df["color"] = geo_df["BATTERY_STATUS"].map(color_map).apply(lambda c: c if isinstance(c, list) else [100, 116, 139])

st.subheader("Live Device Locations")
st.caption("Color indicates battery status: 🟢 ok · 🟡 medium · 🔴 low")

view_state = pdk.ViewState(
    latitude=float(geo_df["LATITUDE"].mean()),
    longitude=float(geo_df["LONGITUDE"].mean()),
    zoom=2,
    pitch=0,
)

layer = pdk.Layer(
    "ScatterplotLayer",
    data=geo_df,
    get_position=["LONGITUDE", "LATITUDE"],
    get_fill_color="color",
    get_radius=60000,
    pickable=True,
    opacity=0.8,
)

deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip={"text": "Device: {DEVICE_ID}\nBattery: {BATTERY}%\nTemp: {TEMPERATURE}°C"},
)

st.pydeck_chart(deck, use_container_width=True)

st.subheader("Device Coordinates")
st.dataframe(
    geo_df[["DEVICE_ID", "LATITUDE", "LONGITUDE", "BATTERY_STATUS", "LAST_SEEN_AT"]],
    use_container_width=True,
    hide_index=True,
)
