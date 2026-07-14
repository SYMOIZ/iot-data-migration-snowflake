# 08 · Lambda Kafka Bridge

**Stack:** `IotHackathon-LambdaKafkaBridge` · **Purpose:** carry IoT Core
messages into Kafka, since the native IoT→Kafka rule action can't talk to the
broker's plaintext listener.

**IaC reference:** `infra/kafka/lambda_bridge/` (`handler.py` + vendored
`kafka-python`) and `infra/kafka/stacks/lambda_bridge_stack.py`.

```
IoT Core rule (iot-events)
   ├─ CloudWatch Logs action   (kept from step 04)
   └─ Lambda action  →  iot-hackathon-lambda-kafka-bridge
                           → produce to Kafka topic iot-events
```

---

## What to create

| Resource | Value |
|---|---|
| Lambda | `iot-hackathon-lambda-kafka-bridge`, Python 3.12, 256 MB, 30s timeout |
| IAM role | `AWSLambdaVPCAccessExecutionRole` (CloudWatch Logs + ENI mgmt) |
| VPC config | private subnet + `<KAFKA_CLIENT_SG_ID>` (so it can reach the broker on 9092) |
| Env vars | `KAFKA_BOOTSTRAP_SERVERS=<KAFKA_BROKER_PRIVATE_IP>:9092`, `KAFKA_TOPIC=iot-events` |

---

## Console steps

1. **Lambda → Create function** → author from scratch, name
   `iot-hackathon-lambda-kafka-bridge`, runtime **Python 3.12**.
2. Upload `infra/kafka/lambda_bridge/` as the deployment package (the handler
   plus the vendored `kafka-python` library — pure Python, no build step).
   Handler: `handler.handler`.
3. **Configuration → General**: memory 256 MB, timeout 30 s.
4. **Configuration → VPC**: attach the project VPC, a **private subnet**, and
   security group `<KAFKA_CLIENT_SG_ID>`.
5. **Configuration → Environment variables**: set the two env vars above.
6. **Configuration → Permissions**: the execution role must include
   `AWSLambdaVPCAccessExecutionRole`.
7. **IoT Core → your rule → Actions → Add** a **Lambda** action pointing at
   this function (keep the existing CloudWatch action). This grants IoT
   permission to invoke the function, scoped to the rule ARN.

## What the function does

Receives the IoT event, converts it to the Kafka Connect **JSON‑with‑schema
envelope** (`{"schema": …, "payload": …}`) required by the JDBC Sink connector
— including a `Timestamp` logical type and epoch‑millis conversion — and
produces it to `iot-events`.

---

## Verification

Start the simulator (or publish a test message in the MQTT test client), then:

- **Lambda → Monitor → Logs (CloudWatch)** shows
  `Received IoT Core event: …` and `Published to Kafka topic=iot-events
  partition=… offset=…`.
- On the broker, consuming `iot-events` shows the new message.

---

## Issues encountered & fixes

1. **Invalid producer arg.** `KafkaProducer(api_version_auto_timeout_ms=…)`
   isn't valid in `kafka-python` 3.0.8 (`Unrecognized configs`). **Fix:**
   remove it; default API‑version auto‑detection works.
2. **Flat JSON silently dropped by the JDBC Sink.** The sink needs a schema
   envelope (see step 09). **Fix:** the Lambda now builds the
   `{"schema": …, "payload": …}` envelope itself before producing.

---

Next: [09 · JDBC Sink Connector](./09-jdbc-sink-connector.md)
