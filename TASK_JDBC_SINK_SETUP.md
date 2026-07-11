# Task: Configure the JDBC Sink Connector

**Date:** 2026-07-11
**Scope:** Install the Confluent JDBC Sink Connector plugin and configure `iot-postgres-sink`
(`iot-events` topic → `iot_platform.iot_events`). **No Debezium, no Snowflake, no dbt.**

---

## Pre-Work: Data Flow Gap Discovered and Addressed

Before configuring the connector, I checked whether real simulator data was actually reaching
`iot-events` yet — it wasn't. The IoT Core Rule was still only routing to CloudWatch Logs (a
placeholder from Task 1.2, deferred pending MSK, never revisited after MSK was dropped). You
approved fixing this properly.

**What was attempted:** created an IoT VPC Destination (`arn:aws:iot:us-east-1:159412676011:ruledestination/vpc/d673fa35-01e3-46ac-859a-7f9869e63d19`, `ENABLED`) and a supporting IAM role
(`iot-hackathon-kafka-vpc-destination-role`) so an IoT Rule Kafka action could reach the broker
inside the VPC.

**Hard blocker found:** AWS IoT's Kafka rule action **rejects `security.protocol=PLAINTEXT`
outright** (API error: valid values are only `SASL_SSL`/`SSL`) and requires the exact class
`org.apache.kafka.common.serialization.ByteBufferSerializer` for values. Our Kafka broker only has
a plaintext listener — making this work requires adding a TLS listener (keystore/certificate) to
the broker itself, which is real additional infrastructure work.

**Decision (yours):** fall back to manual test messages for this task's validation, leave the IoT
Rule unchanged (still CloudWatch Logs only — confirmed untouched), and treat the TLS-enabled
broker listener as a separate future task. The VPC Destination and its IAM role were left in place
(not deleted) since they're reusable once that future work happens — flagging them here rather
than silently leaving them undocumented.

---

## Plugin Installation

Installed on the Kafka Connect instance (`i-08cc1464acf2828a2`):

- **Confluent JDBC Sink Connector v10.9.6** — downloaded from `hub-downloads.confluent.io`
  (official Confluent Hub archive), **MD5-verified** against the published checksum before
  extracting, placed in the persistent `kafka-connect-plugins` volume.
- **PostgreSQL JDBC driver** — the connector bundle already included `postgresql-42.7.11.jar`;
  additionally added `postgresql-42.7.4.jar` from Maven Central (harmless redundancy, connector
  works with either).
- Kafka Connect container restarted to pick up the new plugin path; confirmed via
  `GET /connector-plugins`: `io.confluent.connect.jdbc.JdbcSinkConnector` v10.9.6 listed.

---

## Connector Configuration

Committed at `infra/kafka/connectors/iot-postgres-sink.json` (password shown as a placeholder,
never the real value — see security note below).

```json
{
  "name": "iot-postgres-sink",
  "config": {
    "connector.class": "io.confluent.connect.jdbc.JdbcSinkConnector",
    "tasks.max": "1",
    "topics": "iot-events",
    "connection.url": "jdbc:postgresql://10.42.2.174:5432/iot_platform",
    "connection.user": "iot_platform_app",
    "connection.password": "<from Secrets Manager: iot-hackathon/postgres/iot_platform-credentials>",
    "table.name.format": "iot_events",
    "insert.mode": "insert",
    "auto.create": "false",
    "auto.evolve": "false",
    "pk.mode": "none",
    "errors.tolerance": "all",
    "errors.log.enable": "true",
    "errors.log.include.messages": "true",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "true"
  }
}
```

All required settings match exactly: `insert.mode=insert`, `auto.create=false`,
`auto.evolve=false`, `pk.mode=none`, `errors.tolerance=all`, `errors.log.enable=true`.
`table.name.format=iot_events` was added because the topic name (`iot-events`, hyphen) differs
from the table name (`iot_events`, underscore) — without it the connector would look for a
non-existent table literally named `iot-events`.

Credentials were read from the `iot-hackathon/postgres/iot_platform-credentials` Secrets Manager
secret (created in the previous task) at configuration time.

---

## Issues Encountered and Fixes

### 1. Schemaless records rejected (`pk.mode=none` requires a Struct)

First connector creation succeeded (HTTP 201) and reached `RUNNING`, but the task immediately
`FAILED` on the first real message:

> `Sink connector 'iot-postgres-sink' is configured with 'delete.enabled=false' and 'pk.mode=none' and therefore requires records with a non-null Struct or String value and non-null Struct or String schema, but found record ... with a HashMap value and null value schema.`

Root cause: with `value.converter.schemas.enable=false` (matching the Kafka Connect worker's
global default), messages are parsed as plain JSON maps with no schema — but JDBC Sink requires a
proper Struct (or String) to map fields to columns when `pk.mode=none`.

**Fix:** overrode this connector's `value.converter.schemas.enable` to `true` and used the
standard Kafka Connect "JSON with schema" envelope (`{"schema": {...}, "payload": {...}}`) for
test messages, with the `timestamp` field using Kafka Connect's built-in `Timestamp` logical type
(`"type":"int64","name":"org.apache.kafka.connect.data.Timestamp"`) so it maps correctly to the
`TIMESTAMPTZ` column instead of arriving as an unparsed string.

**Implication for future work:** real IoT Device Simulator messages are flat JSON (no schema
envelope) — they would hit this exact same error if/when the IoT Rule→Kafka wiring is completed.
Whoever picks up that follow-on task will need to either wrap messages in this schema envelope
upstream, or reconsider `pk.mode`/converter settings for schemaless data.

### 2. Wrong instance for `docker exec`

First test-publish attempt ran `docker exec kafka ...` on the **Kafka Connect** instance, which
doesn't have a `kafka` container (`No such container: kafka`) — the broker container lives on the
separate broker instance. Fixed by running the publish command on the correct instance
(`i-0fd77521796b8c71e`).

### 3. Known limitation: REST API exposes the plaintext password (not a bug, not "fixed")

Unlike the earlier PostgreSQL task's credential-exposure bug (an accidental logging mistake, since
fixed), this is different: Kafka Connect's REST API **always** returns the full connector config,
including `connection.password` in plaintext, to anyone who queries `GET /connectors/<name>/config`
or `POST /connectors` — this is how Kafka Connect works by design, without a Secrets Manager
Config Provider plugin installed (a nontrivial additional component, out of this task's scope).
I deliberately avoided rotating the credential over this, since rotation doesn't change the
exposure model — the next status check would show the same thing. Documenting this plainly rather
than presenting it as resolved: **anyone with access to the Kafka Connect REST API on port 8083
(currently restricted to `MskClientSg`/`BastionSg` at the network level) can read this database
password.** A Secrets Manager Config Provider is the correct hardening step if this needs to be
closed later.

---

## Validation Results

| Check | Result |
|---|---|
| Connector status | ✅ `RUNNING` |
| Task status | ✅ `RUNNING` (after the schema fix — was `FAILED` before) |
| Kafka Connect REST API reports RUNNING | ✅ `GET /connectors/iot-postgres-sink/status` |
| Connector consumes from `iot-events` | ✅ 3 test messages published, all consumed |
| Records inserted into PostgreSQL | ✅ all 3 rows present in `iot_platform.iot_events` |

## Sample Inserted Records

```
 id |       device_id       |         timestamp          | latitude | longitude | temperature | humidity | heart_rate | battery
----+-----------------------+----------------------------+----------+-----------+-------------+----------+------------+---------
  1 | device-validation-001 | 2026-07-11 21:41:23.878+00 |  24.8607 |   67.0011 |        29.5 |       62 |         78 |      91
  2 | device-validation-002 | 2026-07-11 21:43:12.766+00 |  24.8615 |    67.002 |        27.1 |       58 |         82 |      87
  3 | device-validation-003 | 2026-07-11 21:43:12.767+00 |   24.859 |   67.0005 |        30.2 |       65 |         74 |      95
```

Note: these are manually-published validation messages, not live simulator telemetry — see the
data flow gap section above. `COUNT(*) FROM iot_events` = 3.

---

## Resources Created This Task

- Kafka Connect plugin: Confluent JDBC Sink Connector v10.9.6 + PostgreSQL JDBC driver
- Kafka Connect connector: `iot-postgres-sink`
- IoT VPC Destination (created but **unused** — TLS blocker, see above): `arn:aws:iot:us-east-1:159412676011:ruledestination/vpc/d673fa35-01e3-46ac-859a-7f9869e63d19`
- IAM role (supporting the above, also unused for now): `iot-hackathon-kafka-vpc-destination-role`

No changes to PostgreSQL infrastructure, Kafka broker, IoT Core rule, or any other existing stack.

---

## Next Step

`iot-postgres-sink` is running and proven to correctly write to PostgreSQL. Awaiting your approval
before Debezium. Two things remain flagged, not started: real IoT Rule→Kafka wiring (needs TLS on
the broker), and the outstanding MSK cleanup task.
