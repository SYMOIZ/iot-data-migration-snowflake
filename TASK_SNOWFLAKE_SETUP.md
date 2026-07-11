# Task: Prepare Snowflake Environment for the Kafka Connector

**Date:** 2026-07-11
**Scope:** Prepare a fresh Snowflake environment from scratch (warehouse, database, schema, role,
user, RSA key-pair auth, grants, Bronze table) and draft the Kafka Connect connector
configuration. **The connector is NOT deployed/registered yet** — this task stops after
generating the SQL and config artifacts, per instructions.

Nothing was assumed to already exist in Snowflake — account `JCANAAG-YCB85704` is a fresh account
with nothing created yet, confirmed by you.

---

## Step 1 — Snowflake SQL (MANUAL — you run this)

File: `infra/snowflake/step1_snowflake_setup.sql`

This is a single, idempotent SQL script (safe to re-run) that creates, in order:

1. **Warehouse** `IOT_INGEST_WH` — `XSMALL`, `AUTO_SUSPEND=60`, `AUTO_RESUME=TRUE`, created
   initially suspended (no cost until first query).
2. **Database** `IOT_PLATFORM`.
3. **Schema** `IOT_PLATFORM.BRONZE`.
4. **Role** `KAFKA_CONNECTOR_ROLE` — dedicated, least-privilege, used by nothing else.
5. **User** `KAFKA_CONNECTOR_USER` — key-pair auth only, `MUST_CHANGE_PASSWORD=FALSE`, no
   password ever set (matches the no-static-password pattern used everywhere else in this
   project — SSM instead of SSH keys, IAM roles instead of access keys, etc.).
6. **RSA public key assignment** (`ALTER USER ... SET RSA_PUBLIC_KEY=...`) — the actual public
   key generated in Step 2 below, embedded directly in the script.
7. **Grants** — the minimum the Snowflake Kafka Connector needs to operate: `USAGE` on the
   warehouse/database, `USAGE` + `CREATE TABLE` + `CREATE STAGE` + `CREATE PIPE` on the schema
   (the connector manages its own internal Snowpipe stage/pipe per topic-partition), and
   `OWNERSHIP` on the Bronze table specifically (the connector needs to manage/alter the table
   it writes to).
8. **Bronze table** `IOT_PLATFORM.BRONZE.IOT_EVENTS_RAW` — two `VARIANT` columns
   (`RECORD_METADATA`, `RECORD_CONTENT`), which is the **standard Snowflake Kafka Connector table
   shape**. This is deliberate for a Bronze layer: it preserves the complete Debezium CDC
   envelope (`before`/`after`/`source`/`op`/`ts_ms`) exactly as received, unparsed —
   schema-on-read. Typed, per-field columns belong in a future Silver-layer dbt model, not here.
9. **Verification queries** at the end (`SHOW`/`DESC` statements) to confirm everything landed
   correctly — in particular `DESC USER KAFKA_CONNECTOR_USER` to confirm the RSA key fingerprint
   is actually set before you approve moving on.

**Run this as `ACCOUNTADMIN`** (or `SECURITYADMIN`+`SYSADMIN` combined) since it creates
warehouses, databases, roles, and users.

---

## Step 2 — AWS Automation (done now)

- **Generated a 2048-bit RSA key pair** (PKCS8, unencrypted private key) using `openssl` directly
  in this session — nothing downloaded, no third-party key generation service.
- **Stored the private key in a new Secrets Manager secret**:
  `iot-hackathon/snowflake/kafka-connector-key` — containing `private_key_pem`, plus the account
  identifier, username, role, warehouse, database, and schema names for convenience. The private
  key **was never printed to any output or committed to the repository** — only the public key
  (non-sensitive by design) appears in the Step 1 SQL script.
- The public key body is embedded directly in `step1_snowflake_setup.sql`'s `ALTER USER`
  statement — you don't need to copy/paste or regenerate anything.

---

## Step 3 — Kafka Connector Configuration (prepared, NOT deployed)

File: `infra/kafka/connectors/iot-snowflake-sink.json`

```json
{
  "name": "iot-snowflake-sink",
  "config": {
    "connector.class": "com.snowflake.kafka.connector.SnowflakeSinkConnector",
    "tasks.max": "1",
    "topics": "cdc.public.iot_events",
    "snowflake.topic2table.map": "cdc.public.iot_events:IOT_EVENTS_RAW",
    "snowflake.url.name": "https://JCANAAG-YCB85704.snowflakecomputing.com:443",
    "snowflake.user.name": "KAFKA_CONNECTOR_USER",
    "snowflake.private.key": "<from Secrets Manager: iot-hackathon/snowflake/kafka-connector-key>",
    "snowflake.role.name": "KAFKA_CONNECTOR_ROLE",
    "snowflake.database.name": "IOT_PLATFORM",
    "snowflake.schema.name": "BRONZE",
    "buffer.count.records": "1",
    "buffer.flush.time": "10",
    "buffer.size.bytes": "1000000",
    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "com.snowflake.kafka.connector.records.SnowflakeJsonConverter",
    "errors.tolerance": "all",
    "errors.log.enable": "true",
    "errors.log.include.messages": "true"
  }
}
```

Notes for when this is actually deployed (not done yet):
- `snowflake.topic2table.map` explicitly pins the topic (which contains dots) to the exact table
  name, rather than relying on the connector's default topic→table name derivation.
- `key.converter`/`value.converter` use Snowflake's own required converters
  (`SnowflakeJsonConverter` is provided by the Snowflake Kafka Connector plugin itself, not a
  generic Kafka Connect converter) — this is Snowflake's documented required configuration, not
  a choice.
- `buffer.count.records=1`/`buffer.flush.time=10` (the Snowflake-enforced minimum) favor fast,
  visible ingestion for validation purposes over batching efficiency — reasonable to revisit for
  a production-scale deployment.
- **Implementation detail for the actual deployment step:** the value stored in Secrets Manager
  is the full PEM (with `-----BEGIN/END PRIVATE KEY-----` headers and newlines); the Snowflake
  connector's `snowflake.private.key` config expects just the base64 body with headers and
  newlines stripped — this stripping needs to happen when the real config is assembled, the same
  way credentials were handled for the JDBC Sink and Debezium connectors.
- The connector plugin itself (`snowflake-kafka-connector` JAR) is **not yet installed** on the
  Kafka Connect worker — that would happen as part of actual deployment, same pattern as the
  JDBC/Debezium/S3 plugin installs.

**Not yet done, waiting for your approval:** installing the plugin, registering this connector,
and the full validation checklist (connector RUNNING, publish an update, verify Debezium emits
it, verify Snowflake receives it, verify the Bronze table has the new record).

---

## Next Step

1. You run `infra/snowflake/step1_snowflake_setup.sql` in Snowsight (as `ACCOUNTADMIN`) and confirm the verification queries at the end look correct — particularly that `DESC USER KAFKA_CONNECTOR_USER` shows a non-null RSA key fingerprint.
2. You approve moving to actual connector deployment.
3. I install the plugin, strip/format the private key correctly, register the connector, and run the full validation checklist from the original task.

Nothing was deployed to Kafka Connect or Snowflake in this task — only SQL/config artifacts were
generated, plus the key pair (public half embedded in the SQL, private half only in Secrets
Manager).
