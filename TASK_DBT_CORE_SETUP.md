# Task: Configure dbt Core

## Summary

dbt Core is deployed and running against Snowflake, transforming the Bronze
CDC data (`IOT_PLATFORM.BRONZE.IOT_EVENTS_RAW`) into a Bronze → Silver → Gold
medallion architecture. All 7 models build successfully and all 33 data tests
pass.

## Where dbt runs

dbt Core + the `dbt-snowflake` adapter are installed in a Python virtualenv
(`/opt/dbt-venv`) on the **Bastion EC2 instance** (`i-0b936de07aea155fb`),
managed entirely via AWS Systems Manager Run Command (no SSH, consistent with
the rest of this project). The project files and the Snowflake private key
were pushed to the instance via SSM; nothing was executed by hand over a
shell session.

- `dbt-core` 1.10.22
- `dbt-snowflake` 1.10.2
- Project: `/opt/dbt/project/iot_platform`
- Profile: `/root/.dbt/profiles.yml`
- Key-pair private key: `/opt/dbt/keys/rsa_key.p8` (mode 600, root-only)

## Snowflake identity

`KAFKA_CONNECTOR_ROLE` (the only Snowflake identity previously available)
has no `CREATE SCHEMA` privilege at the database level — it's scoped
narrowly to Bronze ingestion. Rather than widen the ingestion connector's
permissions, a dedicated, least-privilege role/user was created, matching
the per-service-identity pattern already used throughout this project:

- Role: `DBT_ROLE`
- User: `DBT_USER`
- Auth: RSA key-pair (2048-bit, PKCS8), no password
- Private key: AWS Secrets Manager `iot-hackathon/snowflake/dbt-key`
  (never written to this repo)
- Grants: `USAGE` on warehouse/database/schema(BRONZE), `SELECT` on
  `IOT_EVENTS_RAW`, `CREATE SCHEMA` on `IOT_PLATFORM`

Setup SQL: `infra/snowflake/step_dbt_setup.sql` (run manually by the user as
`ACCOUNTADMIN` in Snowsight — this repo's established pattern for any
privilege grant, since automation has no `ACCOUNTADMIN` access).

Connection:

- Warehouse: `IOT_INGEST_WH`
- Database: `IOT_PLATFORM`
- Schema (default namespace): `BRONZE`

## Project structure

```
dbt/
├── profiles.yml.example              # non-secret template (real file lives on the Bastion instance only)
└── iot_platform/
    ├── dbt_project.yml
    ├── .gitignore                    # target/, dbt_packages/, logs/
    ├── models/
    │   ├── bronze/
    │   │   ├── sources.yml           # source: IOT_PLATFORM.BRONZE.IOT_EVENTS_RAW
    │   │   ├── stg_iot_events.sql    # parses RECORD_METADATA / RECORD_CONTENT VARIANT columns
    │   │   └── schema.yml
    │   ├── silver/
    │   │   ├── iot_events_clean.sql  # deduplicated, typed, quality-filtered
    │   │   └── schema.yml
    │   └── gold/
    │       ├── gold_latest_device_status.sql
    │       ├── gold_avg_temperature_by_device.sql
    │       ├── gold_avg_heart_rate_by_device.sql
    │       ├── gold_battery_health_summary.sql
    │       ├── gold_daily_telemetry_summary.sql
    │       └── schema.yml
    └── tests/                        # (empty — all tests implemented as schema.yml generic tests)
```

## Models created

### Bronze — `stg_iot_events` (view)

Parses the two `VARIANT` columns of `IOT_EVENTS_RAW` (`RECORD_METADATA`,
the Debezium `RECORD_CONTENT` envelope) into relational columns:
`event_id`, `device_id`, `event_timestamp`, `latitude`, `longitude`,
`temperature`, `humidity`, `heart_rate`, `battery`, `operation`
(Debezium op code), plus Kafka offset/partition/create-time metadata.
Uses `COALESCE(after, before)` so delete events still resolve to a usable
row instead of a row of nulls. One row per CDC event — not deduplicated.

### Silver — `iot_events_clean` (table)

One current-state row per `device_id` event: `ROW_NUMBER()` over
`event_id`, ordered by Kafka offset/create-time, keeps only the most recent
CDC version and excludes delete events (`operation != 'd'`). Columns:
`event_id`, `device_id`, `timestamp`, `latitude`, `longitude`,
`temperature`, `humidity`, `heart_rate`, `battery`, `operation`. Basic data
quality filters: `device_id`/`timestamp` not null, latitude/longitude in
valid geographic range, humidity/battery in 0–100.

### Gold (5 business-ready tables)

| Model | Purpose |
|---|---|
| `gold_latest_device_status` | Most recent reading per device + derived `battery_status` (low/medium/ok) — live fleet status |
| `gold_avg_temperature_by_device` | Avg/min/max temperature per device, all-time |
| `gold_avg_heart_rate_by_device` | Avg/min/max heart rate per device, all-time |
| `gold_battery_health_summary` | Fleet-wide device count and avg battery by battery-status bucket |
| `gold_daily_telemetry_summary` | Fleet-wide daily rollup: reading count, active device count, avg temp/humidity/heart rate/battery |

## Tests

33 dbt data tests across all three layers, using `not_null`, `unique`, and
`accepted_values` where appropriate:

- **Bronze** (`stg_iot_events`): `not_null` on `event_id`, `device_id`,
  `event_timestamp`; `not_null` + `accepted_values(['c','r','u','d'])` on
  `operation`
- **Silver** (`iot_events_clean`): `not_null` + `unique` on `event_id`;
  `not_null` on `device_id`, `timestamp`, `latitude`, `longitude`,
  `battery`; `not_null` + `accepted_values(['c','r','u'])` on `operation`
  (delete events are filtered out upstream, so `'d'` is never expected here)
- **Gold**: `not_null` + `unique` on each model's grain column
  (`device_id` / `event_date` / `battery_status`), `not_null` on key
  measures, `accepted_values(['low','medium','ok'])` on `battery_status`

`dbt test` result: **PASS=33, WARN=0, ERROR=0, SKIP=0**.

## Documentation

`dbt docs generate` ran successfully, producing `catalog.json`,
`manifest.json`, and `index.html` in `target/` on the Bastion instance
(not committed — build artifacts, covered by `dbt/iot_platform/.gitignore`,
regenerable at any time with `dbt docs generate`).

## Validation results

```
dbt debug  → All checks passed! (Connection test: OK connection ok)
dbt run    → Done. PASS=7  WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=7
dbt test   → Done. PASS=33 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=33
dbt docs generate → Catalog written to target/catalog.json
```

- Bronze: 1 view model built successfully
- Silver: 1 table model built successfully
- Gold: 5 table models built successfully
- All 33 tests pass
- Documentation generated

## Issues encountered and fixes applied

1. **`KAFKA_CONNECTOR_ROLE` lacked `CREATE SCHEMA`** — confirmed via a live
   `SHOW GRANTS TO ROLE KAFKA_CONNECTOR_ROLE` query; the role only has
   ingestion-scoped grants on `BRONZE`. Fixed by creating a dedicated
   `DBT_ROLE`/`DBT_USER` with its own key pair and a narrowly-scoped
   `CREATE SCHEMA ON DATABASE IOT_PLATFORM` grant, run by the user as
   `ACCOUNTADMIN`.
2. **YAML parse error in `gold/schema.yml`** — unquoted `description: Gold:
   average/min/max temperature...` was parsed as a nested mapping because
   of the `: ` inside the plain scalar. Fixed by quoting the three
   affected descriptions.
3. **`dbt debug` reported missing `git`** — the Bastion instance never had
   git installed. Not a hard blocker (this project has no package
   dependencies), but installed via `dnf` for a clean `dbt debug` pass.
4. **Deprecation warning on `accepted_values`** — dbt 1.10 deprecates
   top-level test arguments in favor of a nested `arguments:` block. Fixed
   across all four `accepted_values` tests (Bronze, Silver, both Gold
   battery-status models).
5. **`invalid identifier 'TIMESTAMP'`** — the generic `not_null` test on
   Silver's `timestamp` column failed because `TIMESTAMP` is a Snowflake
   reserved word and dbt's generated test SQL referenced it unquoted.
   Fixed by adding `quote: true` to that column's definition in
   `silver/schema.yml`, forcing dbt to emit `"timestamp"` in generated SQL.

## Verification performed

Before installing anything, `DBT_ROLE`'s grants and functional
`CREATE SCHEMA` capability were verified live against Snowflake (via a
throwaway `python:3.12-slim` container on an EC2 instance with NAT
internet access, since this session's own outbound proxy blocks
`*.snowflakecomputing.com`):

```
IDENTITY: ('DBT_USER', 'DBT_ROLE', 'IOT_INGEST_WH', 'IOT_PLATFORM', 'BRONZE')
GRANTS TO DBT_ROLE:
 - CREATE SCHEMA ON DATABASE IOT_PLATFORM
 - USAGE ON DATABASE IOT_PLATFORM
 - USAGE ON SCHEMA IOT_PLATFORM.BRONZE
 - SELECT ON TABLE IOT_PLATFORM.BRONZE.IOT_EVENTS_RAW
 - USAGE ON WAREHOUSE IOT_INGEST_WH
CREATE SCHEMA TEST: OK
DROP SCHEMA TEST: OK
BRONZE ROW COUNT: 7
VERIFICATION PASSED
```

The private key was fetched from Secrets Manager only in-memory/on-disk on
EC2 instances for the duration of verification/deployment, and local
scratch copies were shredded (`shred -u`) immediately after use.

## Next step

Streamlit dashboard — **not started, per instruction. Waiting for approval.**
