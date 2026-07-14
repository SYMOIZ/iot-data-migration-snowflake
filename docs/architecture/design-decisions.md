# Design Decisions & Rationale

This document explains the non‑obvious architectural choices and why they were
made. Each was a deliberate decision, not an accident of implementation.

---

## 1. Self‑managed Apache Kafka instead of Amazon MSK

**Decision:** Run Apache Kafka in KRaft mode via Docker Compose on a dedicated
EC2 instance, rather than using Amazon MSK.

**Why:** MSK was initially provisioned but replaced with a self‑managed broker
to reduce cost and to keep full control over the broker configuration and
listeners. KRaft mode removes the need for a separate ZooKeeper ensemble, so a
single container acts as both broker and controller — appropriate for a
single‑node hackathon deployment.

**Trade‑off:** Single‑broker deployment means replication factor 1 and no high
availability. This is an accepted limitation for the project scope.

---

## 2. Lambda bridge instead of the native IoT → Kafka rule action

**Decision:** Route IoT Core messages to Kafka through an AWS Lambda function
(`iot-hackathon-lambda-kafka-bridge`), not the native IoT Rule Kafka action.

**Why:** AWS IoT's Kafka rule action **rejects `security.protocol=PLAINTEXT`**
— it only accepts `SASL_SSL`/`SSL`. The self‑managed broker exposes a
plaintext listener inside the VPC and has no TLS certificate. Adding a TLS
listener (keystore/certificate management) was out of scope, so a small
VPC‑attached Lambda consumes the IoT Rule action and produces to Kafka using
`kafka-python`.

**Bonus benefit:** The Lambda also wraps each event in the Kafka Connect
"JSON with schema" envelope that the JDBC Sink connector requires (see
decision 6), so it doubles as a lightweight transformation point.

---

## 3. Key‑pair authentication for every Snowflake service account

**Decision:** All Snowflake service users (`KAFKA_CONNECTOR_USER`, `DBT_USER`,
`STREAMLIT_USER`) authenticate with RSA key pairs. No Snowflake passwords are
ever set.

**Why:** This mirrors the project‑wide "no static passwords" principle (SSM
instead of SSH keys, IAM roles instead of access keys). Private keys live only
in AWS Secrets Manager and on the instance filesystem with `600` permissions;
the matching public key is registered on the Snowflake user.

---

## 4. One dedicated, least‑privilege role per service

**Decision:** Each consumer of Snowflake gets its own role scoped to exactly
what it needs:

| Role | Purpose | Privileges |
|---|---|---|
| `KAFKA_CONNECTOR_ROLE` | Bronze ingestion | USAGE + CREATE TABLE/STAGE/PIPE on `BRONZE`, OWNERSHIP of `IOT_EVENTS_RAW` |
| `DBT_ROLE` | Transformations | SELECT on Bronze, **CREATE SCHEMA** on the database (to build Silver/Gold) |
| `STREAMLIT_ROLE` | Dashboard reads | SELECT on the Gold schema **only** — no Bronze/Silver visibility, no CREATE |

**Why:** The ingestion connector role has no `CREATE SCHEMA` privilege, so it
cannot be reused by dbt. Rather than widening it, dbt gets its own identity.
The dashboard role is deliberately Gold‑only so the "read only from Gold" rule
is enforced at the database‑privilege layer, not just in application code.

---

## 5. Bronze table as two `VARIANT` columns

**Decision:** `BRONZE.IOT_EVENTS_RAW` has just `RECORD_METADATA VARIANT` and
`RECORD_CONTENT VARIANT`, and the connector's schematization is disabled.

**Why:** This is the standard Snowflake Kafka Connector table shape and it
preserves the **complete Debezium CDC envelope** (`before`/`after`/`source`/
`op`/`ts_ms`) exactly as received. Bronze is schema‑on‑read by design; typed,
per‑field columns are produced downstream by dbt in the Silver layer.

---

## 6. JDBC Sink requires a schema envelope

**Decision:** Messages on the `iot-events` topic carry the Kafka Connect
`{"schema": ..., "payload": ...}` envelope, with `timestamp` as a `Timestamp`
logical type.

**Why:** The JDBC Sink connector runs with `pk.mode=none`, which requires a
proper `Struct` (not a schemaless JSON map) to map fields to columns. The
Lambda bridge therefore emits the schema envelope rather than flat JSON.

---

## 7. Dedicated EC2 host per role

**Decision:** The Kafka broker, Kafka Connect worker, PostgreSQL, and the
Streamlit dashboard each run on their own EC2 instance.

**Why:** Isolation and clarity. Kafka Connect in particular was explicitly
placed on its own instance (the network foundation already had an `8083`
"Kafka Connect REST API" rule prepared for it). The Bastion host is reused as
the dbt execution host since it already has SSM access and network reach into
the VPC.

---

## 8. Streamlit host is the only public resource

**Decision:** The dashboard runs on a new EC2 instance in a **public subnet**
with its own security group allowing inbound `8501`. It imports the existing
network but does not modify the protected `IotHackathon-Network` /
`IotHackathon-Security` stacks.

**Why:** A browsable dashboard needs a public endpoint, but the protected
foundation stacks must not be altered. A new, isolated stack
(`IotHackathon-StreamlitHost`) with its own security group satisfies both
constraints. Every other component stays private and SSM‑only.

---

## 9. `gold_recent_cdc_events` added for the dashboard

**Decision:** A dedicated Gold view exposes row‑level CDC events for the
dashboard's "Operations" and "Raw Data Explorer" pages.

**Why:** The other Gold models are pre‑aggregated, but those pages need
event‑level granularity — and the dashboard is not permitted to query Bronze
or Silver directly. Exposing the data as a Gold view keeps the "Gold only"
rule intact.

---

## 10. Static `device_id` in the simulator payload

**Decision:** The simulator's `device_id` attribute is configured as
`static: true`.

**Why:** With `static: false`, the simulator generates a brand‑new random ID on
every message, so the fleet appears as thousands of one‑off devices instead of
a stable set. Static IDs keep each device's identity constant across its
readings, which every device‑grain Gold model relies on. See
[operations/troubleshooting.md](../operations/troubleshooting.md).
