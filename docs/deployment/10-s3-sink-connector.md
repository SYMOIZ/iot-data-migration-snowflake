# 10 · S3 Sink Connector (Kafka → S3 raw backup)

**Connector:** `iot-s3-sink` · **Purpose:** archive every `iot-events` message
to the S3 backup bucket as date/time‑partitioned JSON — a durable raw copy of
the stream.

**Config file:** `infra/kafka/connectors/iot-s3-sink.json`

---

## Step 1 — Grant the Connect instance S3 access

The Kafka Connect instance role has no S3 access by default. Add a scoped
read/write policy to the **existing backup bucket only**:

- **IAM → Roles → the Kafka Connect instance role → Add permissions** → an
  inline policy allowing `s3:GetObject`/`PutObject`/`ListBucket` on
  `arn:aws:s3:::iot-hackathon-iot-backup-<AWS_ACCOUNT_ID>-us-east-1` and its
  objects.

(The connector uses this instance role via the default credential chain — no
static AWS keys in the config.)

## Step 2 — Install the plugin

Download the **Confluent S3 Sink Connector v12.1.7** from Confluent Hub, verify
its MD5, and extract it into `/opt/kafka-connect/plugins`. Restart the worker
and confirm `S3SinkConnector` appears in `GET /connector-plugins`.

## Step 3 — Register the connector

```json
{
  "name": "iot-s3-sink",
  "config": {
    "connector.class": "io.confluent.connect.s3.S3SinkConnector",
    "tasks.max": "1",
    "topics": "iot-events",
    "s3.bucket.name": "iot-hackathon-iot-backup-<AWS_ACCOUNT_ID>-us-east-1",
    "s3.region": "us-east-1",
    "topics.dir": "raw",
    "format.class": "io.confluent.connect.s3.format.json.JsonFormat",
    "partitioner.class": "io.confluent.connect.storage.partitioner.TimeBasedPartitioner",
    "path.format": "'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH",
    "partition.duration.ms": "3600000",
    "flush.size": "1",
    "errors.tolerance": "all",
    "consumer.override.auto.offset.reset": "latest",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false"
  }
}
```

(Full config, including `locale`/`timezone`/`schema.compatibility`, is in the
committed file.)

- **Partitioning:** objects land at
  `s3://…/raw/iot-events/year=YYYY/month=MM/day=dd/hour=HH/…json`.
- **`flush.size=1`:** flush after every record so writes are immediately
  visible at low volume.

---

## Verification

- Connector + task **RUNNING**.
- Publish a message through the pipeline, then check the bucket: a new JSON
  object appears under the `raw/iot-events/year=…/…` prefix, and its content is
  valid JSON matching the record.

---

## Issue encountered & fix

**Task failed on old, non‑JSON data.** A brand‑new consumer group started from
the **beginning** of `iot-events` and hit a leftover plain‑text test message
from the very first broker validation, which isn't valid JSON. **Fix:** add
`errors.tolerance=all` and `consumer.override.auto.offset.reset=latest` so the
connector starts at the current end of the topic instead of replaying old test
artifacts.

---

Next: [11 · Debezium CDC](./11-debezium-cdc.md)
