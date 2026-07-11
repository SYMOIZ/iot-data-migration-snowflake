# Task: Configure the Kafka Connect S3 Sink

**Date:** 2026-07-11
**Scope:** Install the Confluent S3 Sink Connector and configure `iot-s3-sink`
(`iot-events` topic → S3, raw JSON backup, date/time partitioned). **No Debezium, Snowflake, dbt,
or Streamlit changes** — Debezium's `iot-postgres-cdc` connector (deployed in the prior task)
is untouched and still running.

---

## S3 Bucket: Reused Existing

Checked first, per instructions: `iot-hackathon-iot-backup-159412676011-us-east-1` already exists
(created by `IotHackathon-Security`) — this bucket was already provisioned in the original SRS
specifically as the "Kafka S3 Sink Connector backup bucket." Confirmed accessible and empty, and
reused it rather than creating a new one.

## IAM Permissions

The Kafka Connect instance role (`KafkaConnectInstanceRole`) had no S3 access. Added a scoped
`grant_read_write` to this specific bucket via CDK (`infra/kafka/stacks/kafka_connect_stack.py`)
and deployed — an IAM-only change; the running instance and Kafka Connect container were not
disrupted (confirmed via the CloudFormation diff showing only a policy attachment, no instance
replacement).

## Plugin Installation

- **Confluent S3 Sink Connector v12.1.7** — downloaded from `hub-downloads.confluent.io`,
  **MD5-verified** against the published checksum, installed into the same persistent
  `kafka-connect-plugins` volume already used by the JDBC Sink and Debezium connectors. Kafka
  Connect restarted; all three plugins (`JdbcSinkConnector`, `PostgresConnector`,
  `S3SinkConnector`) confirmed listed via `GET /connector-plugins` afterward — no regressions to
  the existing connectors.

---

## Connector Configuration

Committed at `infra/kafka/connectors/iot-s3-sink.json`.

```json
{
  "name": "iot-s3-sink",
  "config": {
    "connector.class": "io.confluent.connect.s3.S3SinkConnector",
    "tasks.max": "1",
    "topics": "iot-events",
    "s3.bucket.name": "iot-hackathon-iot-backup-159412676011-us-east-1",
    "s3.region": "us-east-1",
    "topics.dir": "raw",
    "storage.class": "io.confluent.connect.s3.storage.S3Storage",
    "format.class": "io.confluent.connect.s3.format.json.JsonFormat",
    "partitioner.class": "io.confluent.connect.storage.partitioner.TimeBasedPartitioner",
    "path.format": "'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH",
    "partition.duration.ms": "3600000",
    "locale": "en-US",
    "timezone": "UTC",
    "flush.size": "1",
    "schema.compatibility": "NONE",
    "errors.tolerance": "all",
    "errors.log.enable": "true",
    "errors.log.include.messages": "true",
    "consumer.override.auto.offset.reset": "latest",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false"
  }
}
```

- **Format:** JSON (`JsonFormat`), as required.
- **Partitioning:** `TimeBasedPartitioner` with `year=YYYY/month=MM/day=dd/hour=HH` — objects land
  at `s3://.../raw/iot-events/year=2026/month=07/day=11/hour=22/...json`.
- **`flush.size=1`:** given the topic's current low message volume, this flushes to S3 after
  every record so writes are visible immediately rather than waiting on a size threshold that
  might not be hit for a long time.
- No AWS credentials in the config — the connector uses the Kafka Connect instance's IAM role
  (default credential provider chain), consistent with the least-exposure pattern used throughout
  this project (no static keys anywhere).

---

## Issue Encountered and Fixed

First connector creation succeeded (HTTP 201, connector `RUNNING`) but the **task immediately
`FAILED`**:

> `SerializationException: JsonParseException: Unrecognized token 'hackathon': was expecting (JSON String, Number, Array, Object...)`

Root cause: this is a brand-new consumer group, so it started reading `iot-events` **from the
beginning** — and hit a leftover plain-text test message (`"hackathon-validation-message"`,
published during the very first Kafka broker validation, several tasks ago) that isn't valid JSON
at all. With no `errors.tolerance` configured (default `none`), this single bad historical record
killed the task.

**Fix:** updated the connector config to add `errors.tolerance=all` / `errors.log.enable=true`
(matching the resilient pattern already used for the JDBC Sink connector) and
`consumer.override.auto.offset.reset=latest`, so the connector starts from the current end of the
topic rather than replaying old test artifacts from earlier, unrelated validation steps — the task
itself asks to verify **new** messages reach S3, not backfill historical test noise. Task moved to
`RUNNING` immediately after.

---

## Validation Results

| Check | Result |
|---|---|
| Connector status | ✅ `RUNNING` |
| Task status | ✅ `RUNNING` (after the offset-reset fix — was `FAILED` before) |
| New Kafka messages written to S3 | ✅ published a message via IoT Core → confirmed it flowed through the full Lambda → Kafka → S3 path |
| New object appears in bucket | ✅ `raw/iot-events/year=2026/month=07/day=11/hour=22/iot-events+1+0000000001.json` |
| JSON format | ✅ object content is valid JSON matching the published record |
| Date/time partitioning | ✅ `year=2026/month=07/day=11/hour=22/` prefix structure confirmed |

### Sample S3 Object Content

```json
{
  "schema": {"name":"iot_event","type":"struct","fields":[...]},
  "payload": {
    "device_id": "device-s3-sink-001",
    "latitude": 24.864,
    "longitude": 67.005,
    "temperature": 25.4,
    "humidity": 70.1,
    "heart_rate": 72.0,
    "battery": 80.0,
    "timestamp": 1783809000000
  }
}
```

---

## Next Step

Raw IoT event backup to S3 is live and verified. Awaiting your approval before Snowflake/dbt/
Streamlit. Still outstanding, untouched: MSK cleanup, and the unused IoT VPC Destination/IAM role
from the earlier abandoned direct-Kafka-rule attempt.
