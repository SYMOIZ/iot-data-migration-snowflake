# 04 · AWS IoT Core

**Purpose:** register a device identity and route incoming `iot-events`
messages onward. The routing target (Lambda) is added in
[step 08](./08-lambda-kafka-bridge.md); for now the rule logs to CloudWatch so
you can prove messages arrive.

---

## What to create

| Resource | Value |
|---|---|
| IoT Policy | `iot-hackathon-device-policy` |
| IoT Thing | `iot-hackathon-wearable-001` |
| Certificate | active, attached to Thing + policy |
| IoT Rule | `iot_hackathon_iot_events_rule` — `SELECT * FROM 'iot-events'` |
| Rule IAM role | `iot-hackathon-iot-rule-role` (CloudWatch Logs write) |
| Log group | `/aws/iotrule/iot-hackathon-iot-events` |

---

## Console steps

### Policy, Thing, certificate

1. **IoT Core → Security → Policies → Create policy** named
   `iot-hackathon-device-policy`. Allow `iot:Connect`, `iot:Publish`,
   `iot:Receive`, and `iot:Subscribe`, scoped to the `iot-events` topic /
   topic filter.
2. **IoT Core → All devices → Things → Create things → Create single thing**
   named `iot-hackathon-wearable-001`. Auto‑generate a new certificate.
3. **Activate** the certificate, then **attach** it to the Thing and attach the
   policy to the certificate (the standard Thing → Certificate → Policy chain).

### Rule (initial: log to CloudWatch)

1. **IoT Core → Message routing → Rules → Create rule** named
   `iot_hackathon_iot_events_rule`.
2. SQL statement: `SELECT * FROM 'iot-events'`.
3. Add action **CloudWatch Logs** → log group
   `/aws/iotrule/iot-hackathon-iot-events`; let the console create the IAM role
   `iot-hackathon-iot-rule-role`.
4. Create the rule.

---

## Verification

1. **IoT Core → MQTT test client → Publish** to `iot-events` with a sample
   payload:

   ```json
   {"device_id":"device-001","latitude":24.8607,"longitude":67.0011,
    "temperature":29.5,"humidity":62,"heart_rate":78,"battery":91,
    "timestamp":"2026-07-11T19:47:00Z"}
   ```

2. **CloudWatch → Log groups → `/aws/iotrule/iot-hackathon-iot-events`** — the
   payload appears within seconds, proving the topic, rule SQL, and rule IAM
   role all work.

## Why the rule starts with only a CloudWatch action

The eventual target is the Lambda bridge, but Lambda doesn't exist yet at this
point in the build order. Logging to CloudWatch first gives an
always‑available way to confirm messages are arriving. In
[step 08](./08-lambda-kafka-bridge.md) you add a **second** action (Lambda)
to this same rule — the CloudWatch action stays for visibility.

> **Design note — why not the native IoT→Kafka action?** AWS IoT's Kafka rule
> action requires TLS (`SASL_SSL`/`SSL`) and rejects the broker's plaintext
> listener. That's why routing to Kafka goes through a Lambda instead. See
> [architecture/design-decisions.md](../architecture/design-decisions.md).

---

Next: [05 · PostgreSQL & Bastion](./05-database-postgresql.md)
