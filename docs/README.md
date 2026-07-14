# Documentation

Complete, reproducible documentation for the IoT → Snowflake data platform.
Read top‑to‑bottom to build the whole project from scratch.

## Start here

1. [Architecture Overview](./architecture/overview.md) — the big picture +
   diagrams
2. [Design Decisions](./architecture/design-decisions.md) — why it's built this
   way
3. [Prerequisites](./deployment/00-prerequisites.md) — accounts, tools, config
   values

## Deployment guide (in order)

| # | Step | Stack / component |
|---|---|---|
| 00 | [Prerequisites](./deployment/00-prerequisites.md) | — |
| 01 | [Network Foundation](./deployment/01-network-foundation.md) | `IotHackathon-Network` |
| 02 | [Security Foundation](./deployment/02-security-foundation.md) | `IotHackathon-Security` |
| 03 | [IoT Device Simulator](./deployment/03-iot-device-simulator.md) | `IotHackathon-DeviceSimulator` |
| 04 | [AWS IoT Core](./deployment/04-iot-core.md) | IoT policy/thing/rule |
| 05 | [PostgreSQL & Bastion](./deployment/05-database-postgresql.md) | `IotHackathon-Database` |
| 06 | [Kafka Broker](./deployment/06-kafka-broker.md) | `IotHackathon-KafkaBroker` |
| 07 | [Kafka Connect](./deployment/07-kafka-connect.md) | `IotHackathon-KafkaConnect` |
| 08 | [Lambda Kafka Bridge](./deployment/08-lambda-kafka-bridge.md) | `IotHackathon-LambdaKafkaBridge` |
| 09 | [JDBC Sink Connector](./deployment/09-jdbc-sink-connector.md) | `iot-postgres-sink` |
| 10 | [S3 Sink Connector](./deployment/10-s3-sink-connector.md) | `iot-s3-sink` |
| 11 | [Debezium CDC](./deployment/11-debezium-cdc.md) | `iot-postgres-cdc` |
| 12 | [Snowflake Bronze](./deployment/12-snowflake-bronze.md) | `iot-snowflake-sink` |
| 13 | [dbt Transformations](./deployment/13-dbt-transformations.md) | `dbt/iot_platform` |
| 14 | [Streamlit Dashboard](./deployment/14-streamlit-dashboard.md) | `IotHackathon-StreamlitHost` |

## Operations

- [End‑to‑End Validation](./operations/validation.md)
- [Troubleshooting](./operations/troubleshooting.md) — every issue + fix
- [Security Model](./operations/security.md)

## Reference

- [Configuration Values](./reference/configuration-values.md) — every
  placeholder explained
- [Screenshots](./screenshots/) — the running dashboard

---

> Placeholders like `<AWS_ACCOUNT_ID>` and `<SNOWFLAKE_ACCOUNT>` are
> environment‑specific values you fill in — never secrets. Real secrets live
> only in AWS Secrets Manager.
