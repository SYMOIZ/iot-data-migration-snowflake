# Task: Deploy Kafka Connect

**Date:** 2026-07-11
**Scope:** Deploy the Kafka Connect worker only. **No connectors were installed** (no JDBC Sink,
no Debezium, no Snowflake connector). PostgreSQL, Debezium, Snowflake, IoT Core, and the old MSK
stack were not touched.

---

## Host Decision

The task as given didn't specify provisioning an EC2 instance, but your earlier "IMPORTANT
IMPLEMENTATION DECISION" explicitly said Kafka Connect should run on **a dedicated EC2 instance**,
and the existing `MskClientSg` security group already had an inbound rule specifically labeled
"Kafka Connect REST API" on port 8083 — clear evidence this was the intended design. Confirmed
with you before proceeding: deployed a new dedicated instance rather than colocating on the
broker.

---

## Resources Created

| Resource | Detail |
|---|---|
| CloudFormation stack | `IotHackathon-KafkaConnect` — CREATE_COMPLETE |
| IAM Role | `KafkaConnectInstanceRole` — `AmazonSSMManagedInstanceCore` only |
| EC2 Instance | `i-08cc1464acf2828a2`, tag `Name=iot-hackathon-kafka-connect` |

### EC2 Specification

| Property | Value |
|---|---|
| Instance ID | `i-08cc1464acf2828a2` |
| Type | t3.large |
| AMI | Amazon Linux 2023 |
| Private IP | `10.42.2.97` |
| Public IP | none |
| Subnet | `subnet-0b48a9b72ff904555` (existing) |
| Security Group | `sg-028a6ec99e24e63cc` (existing `MskClientSg`, reused as-is — already permitted 8083 from `BastionSg`) |
| Access | SSM Session Manager only — no SSH key |

Host setup (Docker, Docker Compose, Java 17) applied the `curl`/`curl-minimal` fix proactively
this time (learned from the broker deployment) — no issues this pass.

---

## Docker Compose Configuration

Full files committed at `infra/kafka/docker-compose.kafka-connect.yml` and
`infra/kafka/connect-distributed.properties`.

```yaml
services:
  kafka-connect:
    image: apache/kafka:4.0.2
    container_name: kafka-connect
    restart: unless-stopped
    network_mode: host
    entrypoint: ["/opt/kafka/bin/connect-distributed.sh"]
    command: ["/mnt/config/connect-distributed.properties"]
    volumes:
      - ./config:/mnt/config
      - kafka-connect-plugins:/opt/kafka-connect/plugins
      - kafka-connect-data:/opt/kafka/logs
volumes:
  kafka-connect-plugins:
  kafka-connect-data:
```

**Image choice:** the official `apache/kafka:4.0.2` image — the exact same image/version already
running as the broker — rather than a separate "Kafka Connect" product image. Kafka Connect
(`connect-distributed.sh`) ships as part of the standard Apache Kafka distribution, so reusing
the identical image guarantees full protocol compatibility with the running broker and satisfies
"official image compatible with the running Kafka version" exactly.

**Key config** (`connect-distributed.properties`): `bootstrap.servers=10.42.2.152:9092` (the
broker's private IP), `group.id=iot-hackathon-connect-cluster`, internal topics
`connect-configs`/`connect-offsets`/`connect-status` (replication factor 1, matching the
single-broker cluster), JSON converters (schemas disabled), REST listener on `0.0.0.0:8083`.

**Persistent volumes:**
- `kafka-connect-plugins` → `/opt/kafka-connect/plugins` — empty now, ready for connector JARs in a future task (`plugin.path` points here)
- `kafka-connect-data` → `/opt/kafka/logs` — worker logs survive container restarts
- Connector *configuration* itself is stored in the `connect-configs` Kafka topic on the broker (Kafka Connect's distributed-mode design — this is how Connect achieves config durability/HA, not local disk)

---

## Running Containers

```
NAME            STATUS          IMAGE
kafka-connect   Up 38 seconds   apache/kafka:4.0.2
```

Restart policy: `unless-stopped`.

---

## REST API Validation

| Check | Result |
|---|---|
| `GET http://localhost:8083/` | ✅ HTTP 200 — `{"version":"4.0.2","commit":"5d0fe56677f97d95","kafka_cluster_id":"5L6g3nShT-eMCtK--X86sw"}` |
| `GET http://localhost:8083/connectors` | ✅ HTTP 200 — `[]` (empty, as required — no connectors installed) |

## Kafka Connectivity Validation

The REST API's `kafka_cluster_id` (`5L6g3nShT-eMCtK--X86sw`) **matches the broker's own cluster
ID** exactly (confirmed against the broker deployment logs from the previous task) — this proves
Kafka Connect didn't just open a TCP connection, it successfully joined the same Kafka cluster.

Further confirmation: listing topics from inside the Connect container against the broker shows
Connect's three internal topics now exist, auto-created by Connect itself on startup:

```
__consumer_offsets
cdc.public.iot_events
connect-configs      ← created by Kafka Connect on this run
connect-offsets      ← created by Kafka Connect on this run
connect-status       ← created by Kafka Connect on this run
iot-events
```

Both pre-existing topics (`iot-events`, `cdc.public.iot_events`) are untouched.

---

## Issues Encountered

None on this deployment — the `curl`/`curl-minimal` package conflict from the broker deployment
was fixed proactively in this instance's UserData before it ran, so host setup succeeded cleanly
on the first attempt.

---

## Next Step

Kafka Connect worker is up, REST API healthy, and confirmed connected to the correct Kafka
cluster. Awaiting approval before installing any plugins or connectors (JDBC Sink, Debezium,
Snowflake). MSK cleanup also remains outstanding, untouched.
