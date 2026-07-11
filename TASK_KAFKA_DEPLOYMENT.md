# Task: Deploy Apache Kafka on the Existing Kafka Broker EC2

**Date:** 2026-07-11
**Scope:** Deploy Apache Kafka (KRaft mode) via Docker Compose on the already-running
`iot-hackathon-kafka-broker` EC2 instance. **Kafka Connect, PostgreSQL, Debezium, and Snowflake
were not touched.** AWS IoT Core and the old MSK stack were not touched either.

---

## Summary

Kafka is running in KRaft mode (no ZooKeeper) on `i-0fd77521796b8c71e`, both required topics
exist and are healthy, and a produce/consume round-trip was validated successfully.

---

## Two Issues Found and Fixed Along the Way

### 1. `bitnami/kafka:3.8` does not exist

The original plan (from `DEPLOYMENT_PLAN.md`) called for the `bitnami/kafka` image. At deploy
time, Docker Hub returned `manifest unknown` — checking directly showed **`bitnami/kafka` now has
zero published tags** (Bitnami restructured its free-tier catalog; free images moved to the frozen
`bitnamilegacy/` namespace, no longer actively maintained).

**Fix:** switched to the **official `apache/kafka`** image instead — actively maintained by the
Apache Kafka project itself, confirmed available (`apache/kafka:4.0.2`).

### 2. Wrong environment variable prefix

The first attempt with `apache/kafka:4.0.2` used `KAFKA_CFG_*`-prefixed environment variables
(e.g. `KAFKA_CFG_PROCESS_ROLES`) — that's the **Bitnami-specific** convention, carried over by
mistake. The official image failed with `Missing required configuration "process.roles"` because
it doesn't recognize `KAFKA_CFG_` at all.

**Fix:** the official image's actual convention (confirmed via research) is just `KAFKA_<PROPERTY>`
with dots replaced by underscores — e.g. `KAFKA_PROCESS_ROLES`, `KAFKA_NODE_ID`,
`KAFKA_CONTROLLER_QUORUM_VOTERS`. Corrected all variable names; deployment succeeded on this pass.

The working configuration is committed at `infra/kafka/docker-compose.kafka.yml`.

---

## Deployment Configuration

| Setting | Value |
|---|---|
| Image | `apache/kafka:4.0.2` (official Apache Kafka image) |
| Mode | KRaft, single-node combined broker+controller (no ZooKeeper) |
| Networking | `network_mode: host` — container shares the host's network namespace |
| Client listener | `PLAINTEXT://0.0.0.0:9092` — internal VPC only, gated by the existing `MskSg` security group (already permits 9092 from `MskClientSg`/`BastionSg`, no changes made) |
| Controller listener | `CONTROLLER://127.0.0.1:9093` — loopback only, not network-exposed at all (KRaft quorum is self-referential on a single node) |
| Persistent storage | Named Docker volume `kafka_kafka-data` → `/var/lib/kafka/data`, backed by the instance's 30 GiB encrypted gp3 root volume |
| Restart policy | `unless-stopped` — auto-restarts on crash or instance reboot, stays down only if explicitly stopped |

Only port 9092 is exposed for internal (VPC) communication; 9093 is loopback-only and not reachable
from the network at all.

---

## Kafka Topics Created

| Topic | Partitions | Replication Factor | Status |
|---|---|---|---|
| `iot-events` | 3 | 1 | Created, healthy (leader=1, ISR=[1] on all partitions) |
| `cdc.public.iot_events` | 3 | 1 | Created, healthy (leader=1, ISR=[1] on all partitions) |

Replication factor is 1 because this is a single-broker deployment (documented risk, consistent
with the approved implementation choice — no HA, acceptable for hackathon scope).

Kafka logged an informational warning when creating `cdc.public.iot_events` ("topics with a period
or underscore could collide" in internal metric names) — this is cosmetic, not an error; the topic
was created successfully and is fully functional.

---

## Validation Results

| Check | Result |
|---|---|
| Kafka container running | ✅ `docker ps` → `Up 36 seconds`, image `apache/kafka:4.0.2` |
| Restart policy configured | ✅ `unless-stopped` |
| Persistent volume configured | ✅ `kafka_kafka-data` → `/var/lib/docker/volumes/kafka_kafka-data/_data` |
| Both topics exist | ✅ `kafka-topics.sh --list` → `cdc.public.iot_events`, `iot-events` |
| Topics healthy | ✅ `--describe` shows Leader=1, ISR=[1] on all 6 partitions (3 per topic) |
| Produce/consume round-trip | ✅ Produced `hackathon-validation-message` to `iot-events`; consumed the same message back successfully |

All checks performed via SSM Run Command — no SSH, no public network exposure.

---

## Next Step

Kafka is up, both topics exist and are verified healthy. Awaiting approval before deploying Kafka
Connect (not started, per instructions). The MSK cleanup task also remains outstanding and
untouched, ready whenever you want it run.
