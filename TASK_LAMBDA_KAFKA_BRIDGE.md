# Task: IoT Core → Lambda → Kafka Bridge

**Date:** 2026-07-11
**Scope:** Replace the direct IoT Rule Kafka action (blocked by AWS IoT's TLS-only requirement,
see `TASK_JDBC_SINK_SETUP.md`) with a Lambda bridge: **AWS IoT Core → AWS Lambda → Apache Kafka**.
No TLS was configured on the broker; the AWS IoT Core Kafka rule action was not used.

---

## Architecture

```
AWS IoT Core (iot_hackathon_iot_events_rule, topic: iot-events)
  ├─ cloudwatchLogs action  →  /aws/iotrule/iot-hackathon-iot-events   (kept, unchanged)
  └─ lambda action          →  iot-hackathon-lambda-kafka-bridge
                                   → KafkaProducer → Kafka broker (10.42.2.152:9092) → iot-events topic
                                   → (existing) iot-postgres-sink connector → PostgreSQL
```

## Resources Created

| Resource | Detail |
|---|---|
| CloudFormation stack | `IotHackathon-LambdaKafkaBridge` — CREATE_COMPLETE |
| Lambda function | `iot-hackathon-lambda-kafka-bridge`, Python 3.12, 256 MB, 30s timeout |
| IAM Role | `LambdaKafkaBridgeRole` — `AWSLambdaVPCAccessExecutionRole` only (covers CloudWatch Logs + ENI management for VPC attachment) |
| Networking | Deployed inside the existing private subnet, using the existing `MskClientSg` security group (already permitted to reach the broker on 9092 — same pattern as Kafka Connect) |
| IoT permission | `lambda:InvokeFunction` granted to `iot.amazonaws.com`, scoped to the specific rule ARN |
| IoT Rule update | `iot_hackathon_iot_events_rule` now has **two** actions: the original `cloudwatchLogs` (kept, per requirement) plus the new `lambda` action |

## Lambda Implementation

- **Runtime:** Python 3.12
- **Library:** `kafka-python` 3.0.8 (pure Python, vendored directly into the deployment package — no native/compiled dependencies, avoids needing Docker-based Lambda bundling)
- **Configuration:** `KAFKA_BOOTSTRAP_SERVERS` and `KAFKA_TOPIC` read from environment variables (not hardcoded)
- **What it does:** receives the IoT Core event, converts it into the Kafka Connect JSON-with-schema envelope the downstream JDBC Sink connector requires (see issue #2 below), and publishes to `iot-events` via `KafkaProducer.send()`

Code: `infra/kafka/lambda_bridge/handler.py`.

---

## Issues Encountered and Fixed

### 1. Invalid kafka-python constructor argument

First deployment's `KafkaProducer(..., api_version_auto_timeout_ms=10000)` failed on every
invocation: `ValueError: Unrecognized configs: {'api_version_auto_timeout_ms': 10000}` — this
parameter doesn't exist in kafka-python 3.0.8's `KafkaProducer`. Removed it; the default API
version auto-detection works fine.

### 2. Flat JSON incompatible with the JDBC Sink connector's schema requirement

After fixing #1, the Lambda successfully published to Kafka, but the messages were **silently
dropped** by `iot-postgres-sink` (visible in Kafka Connect's logs, tolerated per
`errors.tolerance=all` rather than crashing the task):

> `DataException: JsonConverter with schemas.enable requires "schema" and "payload" fields ... If you are trying to deserialize plain JSON data, set schemas.enable=false`

Root cause: the connector (configured in the previous task) requires the Kafka Connect
`{"schema": ..., "payload": ...}` envelope because `pk.mode=none` requires a proper Struct — the
Lambda was forwarding the IoT event as flat JSON.

**Fix:** the Lambda now builds the schema envelope itself before publishing — constructing the
same `struct` schema with a `Timestamp` logical type for the `timestamp` field that was proven to
work in the JDBC Sink task, converting incoming ISO-8601 timestamp strings (or numeric
epoch values) to epoch milliseconds. This is a reasonable reading of "serialize the payload" from
the task requirements, and it's what makes the full chain actually work end-to-end.

**Cost of finding this the hard way:** two validation messages (`device-lambda-bridge-001`,
`device-lambda-bridge-002`) were published before the fix and were correctly tolerated-and-dropped
by the connector — they do **not** appear in PostgreSQL. This is expected and documented, not a
data-loss concern (they were synthetic test messages).

---

## Validation Results

| Step | Result |
|---|---|
| 1. Simulator publishes data | ⚠️ **Not observed live** — the Device Simulator's browser-based simulation session is not currently running (last real event was ~2 hours before this task; simulations need to be manually (re)started in the console UI, which is outside what I can drive). Validated instead with manually-published test messages that exercise the identical IoT Rule → Lambda → Kafka → JDBC path a real simulator message would take. |
| 2. Lambda receives the message | ✅ Confirmed via Lambda CloudWatch Logs: `Received IoT Core event: {...}` |
| 3. Lambda publishes to Kafka | ✅ Confirmed: `Published to Kafka topic=iot-events partition=0 offset=3` |
| 4. Kafka receives the message | ✅ Same log line confirms the broker acknowledged the write (offset assigned) |
| 5. JDBC Sink writes it into PostgreSQL | ✅ Confirmed — `device-lambda-bridge-003` row present in `iot_platform.iot_events` with the correct timestamp, temperature, and battery values |

```
 id |        device_id         |         timestamp          | temperature | battery
----+--------------------------+----------------------------+-------------+---------
  4 | device-lambda-bridge-003 | 2026-07-11 22:00:00+00     |        31.1 |      76
```

**Recommendation:** restart the simulation in the Device Simulator console
(https://d1tlpcp0lb0gga.cloudfront.net) to see live end-to-end flow from real simulated devices —
the pipeline itself is proven working end-to-end with synthetic test data.

---

## Next Step

The full IoT Core → Lambda → Kafka → JDBC Sink → PostgreSQL chain is validated. Awaiting your
approval before Debezium. Still outstanding, untouched: MSK cleanup, and the unused IoT VPC
Destination + IAM role from the earlier (abandoned) direct-Kafka-rule attempt.
