# 12 · Snowflake Bronze + Snowflake Sink Connector

**Purpose:** land the CDC stream (`cdc.public.iot_events`) into Snowflake's
Bronze layer using the Snowflake Kafka Connector (Snowpipe Streaming).

**Files:** `infra/snowflake/step1_snowflake_setup.sql`,
`infra/kafka/connectors/iot-snowflake-sink.json`,
`infra/kafka/Dockerfile.kafka-connect`.

This step has two halves: **(A)** create the Snowflake environment (run SQL in
Snowsight), and **(B)** install + register the connector on Kafka Connect.

---

## A. Snowflake environment (Snowsight)

Generate an RSA key pair for the connector's service user (see
[reference/configuration-values.md](../reference/configuration-values.md)),
store the **private** key in Secrets Manager
(`iot-hackathon/snowflake/kafka-connector-key`), and paste the **public** key
body into the SQL below.

Then, in **Snowsight → Worksheets**, signed in as **`ACCOUNTADMIN`**, run
`infra/snowflake/step1_snowflake_setup.sql`. It creates:

| Object | Detail |
|---|---|
| Warehouse `IOT_INGEST_WH` | XSMALL, `AUTO_SUSPEND=60`, `AUTO_RESUME`, initially suspended |
| Database `IOT_PLATFORM` | — |
| Schema `IOT_PLATFORM.BRONZE` | — |
| Role `KAFKA_CONNECTOR_ROLE` | least‑privilege |
| User `KAFKA_CONNECTOR_USER` | key‑pair auth only (`ALTER USER … SET RSA_PUBLIC_KEY=…`) |
| Grants | USAGE + CREATE TABLE/STAGE/PIPE on BRONZE; OWNERSHIP of the table |
| Table `BRONZE.IOT_EVENTS_RAW` | two `VARIANT` columns: `RECORD_METADATA`, `RECORD_CONTENT` |

The script ends with `SHOW`/`DESC` verification queries — in particular
`DESC USER KAFKA_CONNECTOR_USER` should show a non‑null `RSA_PUBLIC_KEY_FP`.

> **Why two VARIANT columns:** Bronze preserves the full Debezium envelope
> unparsed (schema‑on‑read). dbt parses it into typed columns in Silver. This
> is why the connector sets `snowflake.enable.schematization=false`.

---

## B. Install + register the Snowflake connector

Install **`com.snowflake:snowflake-kafka-connector:4.0.2`** (Snowpipe Streaming)
into `/opt/kafka-connect/plugins`, **with its runtime dependencies**, then
register:

```json
{
  "name": "iot-snowflake-sink",
  "config": {
    "connector.class": "com.snowflake.kafka.connector.SnowflakeStreamingSinkConnector",
    "tasks.max": "1",
    "topics": "cdc.public.iot_events",
    "snowflake.topic2table.map": "cdc.public.iot_events:IOT_EVENTS_RAW",
    "snowflake.url.name": "https://<SNOWFLAKE_ACCOUNT>.snowflakecomputing.com:443",
    "snowflake.user.name": "KAFKA_CONNECTOR_USER",
    "snowflake.private.key": "${secretsManager:iot-hackathon/snowflake/kafka-connector-key:private_key_pem}",
    "snowflake.role.name": "KAFKA_CONNECTOR_ROLE",
    "snowflake.database.name": "IOT_PLATFORM",
    "snowflake.schema.name": "BRONZE",
    "snowflake.enable.schematization": "false",
    "snowflake.streaming.validate.compatibility.with.classic": "false",
    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter.schemas.enable": "false",
    "errors.tolerance": "all",
    "errors.log.enable": "true",
    "errors.log.include.messages": "true"
  }
}
```

---

## Verification

- Connector + task **RUNNING**; the other three connectors stay **RUNNING**.
- Update a row in PostgreSQL; the change flows PostgreSQL → Debezium →
  `cdc.public.iot_events` → Snowflake. Query Bronze:

  ```sql
  SELECT RECORD_CONTENT:after:id::int,
         RECORD_CONTENT:after:device_id::string,
         RECORD_CONTENT:op::string
  FROM IOT_PLATFORM.BRONZE.IOT_EVENTS_RAW
  ORDER BY RECORD_METADATA:CreateTime::string DESC LIMIT 10;
  ```

  The new row appears with `op='u'`. (Snowflake is external SaaS; run
  verification queries from an EC2 instance that has outbound internet via the
  NAT gateway.)

---

## Issues encountered & fixes

The plugin install took several iterations — each caught a real problem:

1. **Not a fat JAR** → `NoClassDefFoundError: BouncyCastleFipsProvider`. **Fix:**
   resolve the full dependency tree (a throwaway Maven container running
   `dependency:copy-dependencies`) instead of the single JAR.
2. **`bcpkix-fips` marked `provided`** in the POM, so Maven excluded it but the
   runtime still needs it. **Fix:** add it as an explicit direct dependency.
3. **Alpine/musl vs glibc.** The connector's native Snowpipe Streaming library
   is glibc‑only; `apache/kafka:4.0.2` is Alpine‑based (`UnsatisfiedLinkError:
   libgcc_s.so.1`, then `__register_atfork: symbol not found` even with
   `gcompat`). **Fix:** rebuild the Connect worker from
   `infra/kafka/Dockerfile.kafka-connect` — a multi‑stage build that copies
   `/opt/kafka` onto `eclipse-temurin:17-jre` (glibc/Ubuntu). Same binaries,
   glibc base. Connectors/state survive because they live in the persistent
   plugins volume and Kafka's internal topics.
4. **Classic‑migration config check.** `SnowflakeStreamingSinkConnector`
   demanded `snowflake.streaming.validate.compatibility.with.classic` be set.
   Not applicable to a fresh deployment. **Fix:** set it to `false`.

---

Next: [13 · dbt Transformations](./13-dbt-transformations.md)
