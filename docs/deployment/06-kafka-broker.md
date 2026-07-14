# 06 · Kafka Broker

**Stack:** `IotHackathon-KafkaBroker` · **Purpose:** the self‑managed Apache
Kafka broker (KRaft mode) that is the central ingest bus.

**IaC reference:** `infra/kafka/` (`kafka_broker_stack.py`,
`docker-compose.kafka.yml`).

---

## What to create

| Resource | Value |
|---|---|
| EC2 | `t3.large`, Amazon Linux 2023, private subnet, no public IP, 30 GiB gp3 encrypted root |
| Security group | `<KAFKA_BROKER_SG_ID>` (allows 9092 from the Kafka‑client SG) |
| IAM role | `AmazonSSMManagedInstanceCore` only |
| Software | Docker, Docker Compose v2, Java 17 |
| Kafka | `apache/kafka:4.0.2`, KRaft single‑node combined broker+controller |
| Topics | `iot-events` (3 partitions), `cdc.public.iot_events` (3 partitions) |

---

## Console + Session Manager steps

1. **EC2 → Launch instance** — Amazon Linux 2023, `t3.large`, project VPC,
   **private subnet**, no public IP, SG `<KAFKA_BROKER_SG_ID>`, IAM role with
   `AmazonSSMManagedInstanceCore`, 30 GiB gp3 encrypted root volume, no key
   pair. Name it `iot-hackathon-kafka-broker`.
2. Wait for **Online** in Fleet Manager, then **Connect → Session Manager**.
3. Install the host software (do **not** install `curl` — see the fix below):

   ```bash
   sudo dnf install -y docker java-17-amazon-corretto-headless unzip
   sudo systemctl enable --now docker
   # Docker Compose v2 plugin
   sudo curl -sL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
     -o /usr/libexec/docker/cli-plugins/docker-compose
   sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
   ```

4. Copy `infra/kafka/docker-compose.kafka.yml` to `/opt/kafka/docker-compose.yml`
   on the instance and start it:

   ```bash
   cd /opt/kafka && sudo docker compose up -d
   ```

   Key facts about that compose file: image `apache/kafka:4.0.2`,
   `network_mode: host`, client listener `PLAINTEXT://0.0.0.0:9092` (VPC‑only),
   controller listener on loopback `127.0.0.1:9093`, a named volume for
   `/var/lib/kafka/data`, and `restart: unless-stopped`.

5. Create the two topics:

   ```bash
   sudo docker exec kafka /opt/kafka/bin/kafka-topics.sh \
     --bootstrap-server localhost:9092 --create --topic iot-events \
     --partitions 3 --replication-factor 1
   sudo docker exec kafka /opt/kafka/bin/kafka-topics.sh \
     --bootstrap-server localhost:9092 --create --topic cdc.public.iot_events \
     --partitions 3 --replication-factor 1
   ```

---

## Verification

- `docker ps` shows the `kafka` container **Up**, image `apache/kafka:4.0.2`.
- `kafka-topics.sh --list` shows both topics; `--describe` shows Leader=1,
  ISR=[1] on all partitions.
- Produce/consume round trip:

  ```bash
  echo "test" | sudo docker exec -i kafka /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 --topic iot-events
  sudo docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 --topic iot-events --from-beginning --max-messages 1
  ```

---

## Issues encountered & fixes

1. **`bitnami/kafka:3.8` no longer exists.** Docker Hub returned `manifest
   unknown` (Bitnami moved free images to a frozen namespace). **Fix:** use the
   official, maintained `apache/kafka:4.0.2` image.
2. **Wrong env‑var prefix.** `KAFKA_CFG_*` is Bitnami‑specific; the official
   image rejected it (`Missing required configuration "process.roles"`).
   **Fix:** use `KAFKA_<PROPERTY>` names (e.g. `KAFKA_PROCESS_ROLES`,
   `KAFKA_NODE_ID`, `KAFKA_CONTROLLER_QUORUM_VOTERS`).
3. **`curl`/`curl-minimal` conflict** (same as the database host) — don't
   install `curl` explicitly.

> **Note:** replication factor is 1 because this is a single broker (accepted
> limitation for the project scope — no HA).

---

Next: [07 · Kafka Connect](./07-kafka-connect.md)
