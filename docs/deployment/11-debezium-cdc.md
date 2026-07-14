# 11 · Debezium CDC (PostgreSQL → Kafka)

**Connector:** `iot-postgres-cdc` · **Purpose:** stream row‑level changes from
`iot_platform.iot_events` into the Kafka topic `cdc.public.iot_events`, which
Snowflake consumes.

**Config file:** `infra/kafka/connectors/iot-postgres-cdc.json`

This is what makes the pipeline a true **change‑data‑capture** flow: inserts,
updates, and deletes in PostgreSQL are captured from the write‑ahead log via
logical replication (`pgoutput`).

---

## Prerequisites (already satisfied)

From [step 05](./05-database-postgresql.md): `wal_level=logical`,
`max_replication_slots=10`, `max_wal_senders=10`, and the `iot_platform_app`
role has the `REPLICATION` attribute. No replication slot or publication exists
yet — Debezium creates them on first start.

## Install the plugin

Download the **Debezium PostgreSQL connector v3.6.0.Final** (the self‑contained
`-plugin.tar.gz` from Maven Central), verify its SHA1, extract into
`/opt/kafka-connect/plugins`, restart the worker, and confirm
`io.debezium.connector.postgresql.PostgresConnector` in `GET
/connector-plugins`.

## Register the connector

```json
{
  "name": "iot-postgres-cdc",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "database.hostname": "<POSTGRES_PRIVATE_IP>",
    "database.port": "5432",
    "database.user": "iot_platform_app",
    "database.password": "${secretsManager:iot-hackathon/postgres/iot_platform-credentials:password}",
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

- **`topic.prefix=cdc` + `table.include.list=public.iot_events`** →
  `<prefix>.<schema>.<table>` = `cdc.public.iot_events` (the topic created in
  step 06).
- **`plugin.name=pgoutput`** is PostgreSQL's built‑in logical decoding — no
  database extension needed.
- **`slot.name` / `publication.name`** are created automatically by Debezium
  on first start (`publication.autocreate.mode=filtered`).

---

## Verification

- Connector + task **RUNNING**.
- In PostgreSQL, `pg_replication_slots` shows `debezium` (`pgoutput`, `active=t`)
  and `pg_publication` shows `iot_events_publication` scoped to
  `public.iot_events`.
- Update a row (`UPDATE iot_events SET battery=55.5 WHERE id=1;`), then consume
  `cdc.public.iot_events` — a CDC event appears with `"op":"u"` and the new
  values.

### The CDC envelope

Each message is a Debezium envelope; downstream (Snowflake + dbt) reads the
`after` image and `op`:

```json
{ "before": null,
  "after": { "id": 1, "device_id": "…", "temperature": 33.3, "battery": 55.5, … },
  "source": { "connector": "postgresql", "table": "iot_events", "lsn": 31806888 },
  "op": "u", "ts_ms": 1783808086188 }
```

On first start Debezium also performs an **initial snapshot** of existing rows
(`"op":"r"`) before streaming live changes — expected behavior.

---

Next: [12 · Snowflake Bronze](./12-snowflake-bronze.md)
