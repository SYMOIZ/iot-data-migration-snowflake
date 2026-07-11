# Task: Deploy Debezium CDC

**Date:** 2026-07-11
**Scope:** Install the Debezium PostgreSQL connector plugin and configure `iot-postgres-cdc`
(`iot_platform.iot_events` → `cdc.public.iot_events`). **No Snowflake, no dbt, no Streamlit.**

---

## Plugin Installation

Installed on the Kafka Connect instance (`i-08cc1464acf2828a2`):

- **Debezium PostgreSQL Connector v3.6.0.Final** — downloaded directly from Maven Central
  (`io.debezium:debezium-connector-postgres`, official self-contained `-plugin.tar.gz` bundle
  including all dependencies), **SHA1-verified** against the published checksum before
  extracting, placed in the same persistent `kafka-connect-plugins` volume already used by the
  JDBC Sink connector.
- Kafka Connect container restarted; confirmed via `GET /connector-plugins`:
  `io.debezium.connector.postgresql.PostgresConnector` v3.6.0.Final listed alongside the
  existing JDBC Sink plugin (unaffected by the restart).

---

## Pre-Check: Existing Replication State

Before configuring anything, checked PostgreSQL directly: no existing replication slot or
publication (`pg_replication_slots` and `pg_publication` both empty), so this task created new
ones rather than reusing. The `iot_platform_app` role already has the `REPLICATION` attribute
(granted during the earlier PostgreSQL setup task specifically for this purpose) — no role change
needed. `wal_level=logical`, `max_replication_slots=10`, `max_wal_senders=10` — ample headroom.

---

## Connector Configuration

Committed at `infra/kafka/connectors/iot-postgres-cdc.json` (password as a Secrets Manager
placeholder, matching the pattern from the JDBC Sink connector's committed config — never the
real value).

```json
{
  "name": "iot-postgres-cdc",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "database.hostname": "10.42.2.174",
    "database.port": "5432",
    "database.user": "iot_platform_app",
    "database.password": "<from Secrets Manager: iot-hackathon/postgres/iot_platform-credentials>",
    "database.dbname": "iot_platform",
    "topic.prefix": "cdc",
    "table.include.list": "public.iot_events",
    "plugin.name": "pgoutput",
    "slot.name": "debezium",
    "publication.name": "iot_events_publication",
    "publication.autocreate.mode": "filtered",
    "decimal.handling.mode": "double",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false"
  }
}
```

Key decisions:
- `plugin.name=pgoutput` — PostgreSQL 16's built-in logical decoding plugin, no extra database
  extension needed (already confirmed available when WAL was configured).
- `topic.prefix=cdc` + `table.include.list=public.iot_events` → Debezium's default topic naming
  (`<prefix>.<schema>.<table>`) produces exactly `cdc.public.iot_events`, the topic already
  created in the earlier Kafka topics task — no new topic had to be created.
- `slot.name=debezium`, `publication.name=iot_events_publication`,
  `publication.autocreate.mode=filtered` — since neither existed, Debezium created both
  automatically on first connector start (its standard "use if present, else create" behavior),
  satisfying the requirement without manual SQL.
- Reused the network path already proven by the JDBC Sink connector (`PostgresSg` already permits
  inbound 5432 from `MskClientSg`) — no security group changes needed.

---

## Validation Results

| Check | Result |
|---|---|
| Connector status | ✅ `RUNNING` |
| Task status | ✅ `RUNNING` — first attempt, no errors |
| Replication slot active | ✅ `pg_replication_slots`: `debezium \| pgoutput \| logical \| active=t \| active_pid=7326` |
| Publication active | ✅ `pg_publication`: `iot_events_publication`, correctly scoped via `pg_publication_tables` to exactly `public.iot_events` |
| Record updated in PostgreSQL | ✅ `UPDATE iot_events SET battery=55.5, temperature=33.3 WHERE id=1` |
| CDC event appears in Kafka | ✅ Consumed from `cdc.public.iot_events`: update event captured with `"op":"u"`, `id:1`, new values `temperature:33.3, battery:55.5` |

### CDC Event Sample (the update)

```json
{
  "before": null,
  "after": {
    "id": 1,
    "device_id": "device-validation-001",
    "timestamp": "2026-07-11T21:41:23.878000Z",
    "latitude": 24.8607,
    "longitude": 67.0011,
    "temperature": 33.3,
    "humidity": 62.0,
    "heart_rate": 78.0,
    "battery": 55.5
  },
  "source": {
    "version": "3.6.0.Final",
    "connector": "postgresql",
    "db": "iot_platform",
    "schema": "public",
    "table": "iot_events",
    "lsn": 31806888
  },
  "op": "u",
  "ts_ms": 1783808086188
}
```

(`"before": null` is expected here — `REPLICA IDENTITY DEFAULT` on `iot_events` only captures the
primary key in the before-image for updates, not full old-row contents; the `after` image and
`op:"u"` are what matter for validating the CDC event itself.)

On connector startup, Debezium also performed its standard **initial snapshot** of the table's 4
existing rows (`"op":"r"`, read/snapshot events) before switching to streaming live changes — this
is expected, correct Debezium behavior, not an error.

---

## Next Step

Debezium CDC is running and proven to correctly capture PostgreSQL changes into
`cdc.public.iot_events`. Awaiting your approval before Snowflake. Still outstanding, untouched:
MSK cleanup, and the unused IoT VPC Destination/IAM role from the earlier direct-Kafka-rule
attempt.
