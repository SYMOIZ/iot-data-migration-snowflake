# 13 · dbt Transformations (Bronze → Silver → Gold)

**Purpose:** transform the raw Bronze CDC envelopes into cleaned, typed Silver
data and business‑ready Gold marts.

**Files:** `dbt/iot_platform/` (the dbt project), `dbt/profiles.yml.example`,
`infra/snowflake/step_dbt_setup.sql`.

dbt runs on the **Bastion** EC2 instance (it already has SSM access and VPC
reach). There's no console for dbt — you run it from the Bastion Session
Manager shell.

---

## A. Snowflake role for dbt (Snowsight)

The ingestion role can't create schemas, so dbt gets its own identity.
Generate a key pair, store the private key in
`iot-hackathon/snowflake/dbt-key`, paste the public key into
`infra/snowflake/step_dbt_setup.sql`, and run it in Snowsight as
`ACCOUNTADMIN`. It creates:

| Object | Privileges |
|---|---|
| Role `DBT_ROLE` | USAGE on warehouse/database/BRONZE, SELECT on `IOT_EVENTS_RAW`, **CREATE SCHEMA** on `IOT_PLATFORM` |
| User `DBT_USER` | key‑pair auth only |

## B. Install dbt on the Bastion

In the Bastion Session Manager shell:

```bash
sudo dnf install -y python3-pip python3-devel gcc git
python3 -m venv /opt/dbt-venv
/opt/dbt-venv/bin/pip install dbt-core dbt-snowflake
```

## C. Configure the profile

Copy `dbt/profiles.yml.example` to `/root/.dbt/profiles.yml` and fill in your
values. It uses **key‑pair auth** (`authenticator: snowflake_jwt`), pointing at
the private key file fetched from Secrets Manager onto the instance
(`/opt/dbt/keys/rsa_key.p8`, mode `600`):

```yaml
iot_platform:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: <SNOWFLAKE_ACCOUNT>
      user: DBT_USER
      role: DBT_ROLE
      authenticator: snowflake_jwt
      private_key_path: /opt/dbt/keys/rsa_key.p8
      warehouse: IOT_INGEST_WH
      database: IOT_PLATFORM
      schema: BRONZE
      threads: 4
```

## D. Run dbt

Copy the `dbt/iot_platform/` project onto the instance and run:

```bash
cd /opt/dbt/project/iot_platform
/opt/dbt-venv/bin/dbt debug     # all checks pass
/opt/dbt-venv/bin/dbt run       # builds all models
/opt/dbt-venv/bin/dbt test      # runs all data tests
/opt/dbt-venv/bin/dbt docs generate
```

---

## Models

**Bronze** (`models/bronze/`)
- `stg_iot_events` (view) — parses the `RECORD_METADATA`/`RECORD_CONTENT`
  VARIANT columns into typed columns, using `COALESCE(after, before)` so delete
  events still resolve.

**Silver** (`models/silver/`)
- `iot_events_clean` (table) — one current‑state row per `event_id` (most
  recent CDC version by Kafka offset), delete events excluded, with quality
  filters (valid lat/long, humidity/battery 0–100).

**Gold** (`models/gold/`)
- `gold_latest_device_status` — most recent reading per device + battery status
- `gold_avg_temperature_by_device`, `gold_avg_heart_rate_by_device`
- `gold_battery_health_summary` — fleet battery buckets
- `gold_daily_telemetry_summary` — per‑day fleet rollup
- `gold_recent_cdc_events` (view) — row‑level events for the dashboard's
  Operations / Raw Data Explorer pages

## Tests

`not_null`, `unique`, and `accepted_values` across all layers (e.g. `operation`
∈ `c,r,u,d`; `battery_status` ∈ `low,medium,ok`), defined in each layer's
`schema.yml`.

## Keeping Gold fresh

Silver/Gold are **tables** (snapshots), so they don't reflect new Bronze rows
until `dbt run` runs again. A cron job on the Bastion refreshes them every 5
minutes:

```
*/5 * * * * /opt/dbt/run_dbt.sh   # runs `dbt run`, logs to /var/log/dbt-refresh.log
```

---

## Issues encountered & fixes

1. **`dbt debug` reports missing `git`.** Not fatal, but install `git` for a
   clean pass.
2. **YAML parse error** from an unquoted `description: Gold: …` (the `: `
   looked like a nested mapping). **Fix:** quote such descriptions.
3. **Deprecated `accepted_values` syntax** — nest the args under `arguments:`.
4. **`invalid identifier 'TIMESTAMP'`** — `timestamp` is a Snowflake reserved
   word and the generated test SQL referenced it unquoted. **Fix:** add
   `quote: true` to that column in `schema.yml`.
5. **Schema names are `BRONZE_*`.** dbt concatenates the default schema
   (`BRONZE`) with each model's `+schema`, so the layers materialize as
   `BRONZE_BRONZE`, `BRONZE_SILVER`, `BRONZE_GOLD`. The dashboard reads
   `BRONZE_GOLD`. See
   [operations/troubleshooting.md](../operations/troubleshooting.md).

---

Next: [14 · Streamlit Dashboard](./14-streamlit-dashboard.md)
