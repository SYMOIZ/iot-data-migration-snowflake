"""Snowflake connection for the IoT Analytics dashboard.

Reads only from the dbt Gold layer. The STREAMLIT_ROLE identity used here
has no grants on BRONZE or SILVER and no CREATE privileges at all - the
"Gold only" rule is enforced by Snowflake, not just by which tables this
app happens to query.
"""

import streamlit as st
import snowflake.connector
from cryptography.hazmat.primitives import serialization


class ConnectionError(Exception):
    pass


@st.cache_resource(show_spinner=False)
def get_connection():
    try:
        cfg = st.secrets["snowflake"]
    except Exception as exc:
        raise ConnectionError(
            "Missing Snowflake configuration (.streamlit/secrets.toml). "
            "See .streamlit/secrets.toml.example."
        ) from exc

    try:
        with open(cfg["private_key_path"], "rb") as f:
            p_key = serialization.load_pem_private_key(f.read(), password=None)
        private_key_bytes = p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    except FileNotFoundError as exc:
        raise ConnectionError(
            f"Private key not found at {cfg['private_key_path']!r}."
        ) from exc

    try:
        return snowflake.connector.connect(
            account=cfg["account"],
            user=cfg["user"],
            role=cfg["role"],
            warehouse=cfg["warehouse"],
            database=cfg["database"],
            schema=cfg["schema"],
            private_key=private_key_bytes,
            client_session_keep_alive=True,
        )
    except Exception as exc:
        raise ConnectionError(f"Could not connect to Snowflake: {exc}") from exc


def test_connection() -> tuple[bool, str]:
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            user, role, wh = cur.fetchone()
            return True, f"Connected as {user} ({role}) on {wh}"
        finally:
            cur.close()
    except ConnectionError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Unexpected connection error: {exc}"
