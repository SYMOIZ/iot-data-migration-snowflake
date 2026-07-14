# 07 · Kafka Connect

**Stack:** `IotHackathon-KafkaConnect` · **Purpose:** the Kafka Connect worker
(distributed mode) that hosts all four connectors added in later steps.

**IaC reference:** `infra/kafka/` (`kafka_connect_stack.py`,
`docker-compose.kafka-connect.yml`, `connect-distributed.properties`,
`Dockerfile.kafka-connect`).

---

## What to create

| Resource | Value |
|---|---|
| EC2 | `t3.large`, Amazon Linux 2023, private subnet, no public IP |
| Security group | `<KAFKA_CLIENT_SG_ID>` (already allows 8083 from Bastion) |
| IAM role | `AmazonSSMManagedInstanceCore` (S3 read/write is added in step 10) |
| Worker | Kafka Connect (distributed), REST API on `0.0.0.0:8083` |

---

## Console + Session Manager steps

1. **EC2 → Launch instance** — Amazon Linux 2023, `t3.large`, private subnet,
   no public IP, SG `<KAFKA_CLIENT_SG_ID>`, IAM role with
   `AmazonSSMManagedInstanceCore`. Name it `iot-hackathon-kafka-connect`.
   Install Docker + Compose + Java exactly as on the broker (again, **don't**
   install `curl`).
2. Copy these files onto the instance:
   - `docker-compose.kafka-connect.yml`
   - `connect-distributed.properties` → set
     `bootstrap.servers=<KAFKA_BROKER_PRIVATE_IP>:9092`
   - `Dockerfile.kafka-connect` (used later for the Snowflake connector — it
     rebuilds the worker on a glibc base image; see step 12)
3. Start the worker:

   ```bash
   sudo docker compose -f docker-compose.kafka-connect.yml up -d --build
   ```

Key config facts (`connect-distributed.properties`):
`group.id=iot-hackathon-connect-cluster`; internal topics `connect-configs`/
`connect-offsets`/`connect-status` (replication factor 1); JSON converters
(schemas disabled globally — individual connectors override as needed);
`plugin.path=/opt/kafka-connect/plugins` (a persistent Docker volume that
holds every connector JAR you install later).

---

## Verification

```bash
curl -s http://localhost:8083/                 # {"version":"4.0.2", ...}
curl -s http://localhost:8083/connectors       # []  (no connectors yet)
```

Confirm Connect actually **joined the broker's cluster** (not just opened a
socket): the `kafka_cluster_id` returned by `GET /` matches the broker's
cluster id, and listing topics shows Connect auto‑created its three internal
`connect-*` topics.

## Why a dedicated instance / why the same image

Kafka Connect runs on its own EC2 instance (the network foundation already had
an `8083` "Kafka Connect REST API" rule prepared for it). The worker uses the
**same `apache/kafka:4.0.2`** distribution as the broker —
`connect-distributed.sh` ships inside standard Kafka — guaranteeing protocol
compatibility. Connector configuration is stored durably in the
`connect-configs` Kafka topic, not on local disk.

---

Next: [08 · Lambda Kafka Bridge](./08-lambda-kafka-bridge.md)
