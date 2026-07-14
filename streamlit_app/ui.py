import datetime as dt

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from connection import test_connection

REFRESH_INTERVAL_MS = 30_000

CUSTOM_CSS = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    div[data-testid="stMetric"] {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 14px 18px;
    }
    div[data-testid="stMetricLabel"] {
        font-weight: 600;
        color: #475569;
    }
    h1, h2, h3 {
        color: #0F172A;
    }
    .app-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #E2E8F0;
        margin-bottom: 1.2rem;
    }
    .app-header h1 {
        margin: 0;
        font-size: 1.6rem;
    }
    .app-header .subtitle {
        color: #64748B;
        font-size: 0.85rem;
    }
    .status-pill {
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-ok { background-color: #DCFCE7; color: #166534; }
    .status-warn { background-color: #FEF9C3; color: #854D0E; }
    .status-error { background-color: #FEE2E2; color: #991B1B; }
</style>
"""


def page_header(title: str, subtitle: str = ""):
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="app-header">
            <div>
                <h1>📡 IoT Analytics Platform</h1>
                <div class="subtitle">{title}{" — " + subtitle if subtitle else ""}</div>
            </div>
            <div class="subtitle">Last refreshed: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def enable_autorefresh(key: str):
    st_autorefresh(interval=REFRESH_INTERVAL_MS, key=key)


def connection_sidebar():
    st.sidebar.markdown("### Connection")
    ok, message = test_connection()
    if ok:
        st.sidebar.markdown(
            f'<span class="status-pill status-ok">● Connected</span>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f'<span class="status-pill status-error">● Disconnected</span>',
            unsafe_allow_html=True,
        )
    st.sidebar.caption(message)
    st.sidebar.markdown("---")
    st.sidebar.caption("Data source: Snowflake `IOT_PLATFORM.BRONZE_GOLD` (dbt Gold models only)")
    st.sidebar.caption("Auto-refresh: every 30 seconds")
    return ok
