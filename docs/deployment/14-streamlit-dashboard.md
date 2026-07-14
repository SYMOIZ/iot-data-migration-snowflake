# 14 · Streamlit Dashboard

**Stack:** `IotHackathon-StreamlitHost` · **Purpose:** a live analytics
dashboard reading **only** the dbt Gold models.

**Files:** `streamlit_app/` (the app), `infra/streamlit/` (CDK host stack +
systemd unit), `infra/snowflake/step_streamlit_setup.sql`.

This is the only public component: a dedicated EC2 instance in a **public
subnet** with its own security group. It imports the existing network but does
not modify the protected foundation stacks.

---

## A. Snowflake role for the dashboard (Snowsight)

Generate a key pair, store the private key in
`iot-hackathon/snowflake/streamlit-key`, paste the public key into
`infra/snowflake/step_streamlit_setup.sql`, and run it as `ACCOUNTADMIN`. It
creates a **read‑only, Gold‑only** identity:

| Object | Privileges |
|---|---|
| Role `STREAMLIT_ROLE` | USAGE on warehouse/database + the Gold schema; SELECT on Gold tables/views **only** |
| User `STREAMLIT_USER` | key‑pair auth only |

> The Gold schema is physically `IOT_PLATFORM.BRONZE_GOLD` (see the dbt
> schema‑naming note). Granting SELECT there — and nowhere else — enforces
> "read only from Gold" at the database level.

## B. Deploy the host

**IaC reference:** `infra/streamlit/` (CDK). Or via console:

1. **EC2 → Launch instance** — Amazon Linux 2023, `t3.small`, project VPC,
   **public subnet**, **Auto‑assign public IP = Enable**, a **new** security
   group allowing inbound **TCP 8501 from `0.0.0.0/0`**, IAM role with
   `AmazonSSMManagedInstanceCore`, no key pair. Name it
   `iot-hackathon-streamlit-dashboard`.
2. Install Python tooling and the app dependencies
   (`streamlit`, `snowflake-connector-python`, `pandas`, `pydeck`,
   `streamlit-autorefresh` — see `streamlit_app/requirements.txt`).
3. Copy `streamlit_app/` to `/opt/streamlit/app`, place the private key at
   `/opt/streamlit/keys/rsa_key.p8` (mode `600`), and create
   `/opt/streamlit/app/.streamlit/secrets.toml` from
   `secrets.toml.example` (schema = `BRONZE_GOLD`).
4. Install and start the systemd service `infra/streamlit/streamlit.service`
   (`restart=on-failure`, runs `streamlit run Home.py`).

## C. Open the dashboard

Find the instance's public IP in **EC2 → Instances** (or the CloudFormation
stack outputs) and browse to `http://<public-ip>:8501`.

---

## Dashboard pages

| Page | Content |
|---|---|
| Executive Overview | KPI cards: devices, records, active devices, avg temp/heart‑rate/battery; daily volume |
| Device Health | latest status (battery‑colored), battery health, offline devices |
| Telemetry Analytics | temperature / heart‑rate / humidity trends; daily volume |
| Device Map | pydeck scatter of device lat/long, colored by battery status |
| Operations | last data arrival, derived pipeline health, latest CDC events |
| Raw Data Explorer | search by device id, date filter, CSV export |

Features: sidebar navigation, connection‑status indicator, **auto‑refresh every
30 s**, loading spinners, and error banners (never raw stack traces).

Screenshots: [../screenshots/](../screenshots/).

---

## Verification

- The sidebar shows **● Connected** as `STREAMLIT_USER (STREAMLIT_ROLE)`.
- All six pages render live Gold data; filters and CSV export work.
- A negative check confirms `STREAMLIT_ROLE` **cannot** read Bronze/Silver
  (access denied) — the Gold‑only guarantee.

---

## Issues encountered & fixes

1. **"Not connected / no data" despite the SQL being run.** The setup SQL and
   `secrets.toml` targeted a schema literally named `GOLD`, but dbt materializes
   Gold as `BRONZE_GOLD`. **Fix:** point the role grants and the app at
   `IOT_PLATFORM.BRONZE_GOLD`.
2. **Map tiles blank in headless screenshots.** A screenshot‑tooling artifact
   (restricted outbound in the capture environment), not a dashboard bug — a
   normal browser loads the basemap fine.

---

This is the final deployment step. For end‑to‑end validation and teardown, see
[operations/validation.md](../operations/validation.md) and
[operations/troubleshooting.md](../operations/troubleshooting.md).
