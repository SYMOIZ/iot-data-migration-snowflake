# Troubleshooting

Every issue encountered during this build, its root cause, and the exact fix —
consolidated so you can search one place. Issues are also noted inline in each
[deployment step](../deployment/).

---

## Simulator "running" but no data reaches the pipeline

The single highest‑impact failure. The simulator can run continuously and log
success while **zero** data reaches Kafka, because the misconfiguration is in
the device‑type definition and produces no error anywhere.

**Root causes (all three must be correct):**
1. **MQTT topic** must be exactly `iot-events`. If it holds descriptive text,
   messages publish to a topic the IoT Rule never matches.
2. **Payload field names** must match the pipeline exactly: `device_id`,
   `timestamp`, `latitude`, `longitude`, `temperature`, `humidity`,
   `heart_rate`, `battery` — flat, not nested. Names like `Humidity`,
   `heartrate`, `Battery`, or a nested `location` object break the Lambda
   bridge's field lookups.
3. **`device_id` must be `static: true`.** Otherwise every message gets a new
   random id and each reading looks like a new device, inflating device counts
   and breaking device‑grain Gold models.

**Fix:** correct the device type (topic + field names + static id), then
**stop and restart** the simulation so a fresh run picks up the change.
Verify with the Bronze row‑count query in [validation.md](./validation.md).

---

## AWS / OS issues

| Symptom | Cause | Fix |
|---|---|---|
| `dnf` aborts installing `curl` | AL2023 ships `curl-minimal`, which conflicts with `curl` | Don't install `curl`; `curl-minimal` suffices |
| CloudFormation fails on the simulator template | Stock template pins Lambdas to `nodejs18.x` (blocked for new functions) | Use the patched template (`nodejs20.x`) in `infra/device-simulator/` |
| AWS CLI: `InvalidClientTokenId` | Sandbox env vars shadow the real profile | Ensure the intended credentials aren't overridden by `AWS_*` env vars |

## Kafka / Kafka Connect

| Symptom | Cause | Fix |
|---|---|---|
| `manifest unknown` for `bitnami/kafka` | Bitnami moved free images to a frozen namespace | Use `apache/kafka:4.0.2` |
| `Missing required configuration "process.roles"` | Used Bitnami `KAFKA_CFG_*` env vars | Use `KAFKA_<PROPERTY>` names |
| `No such container: kafka` | Ran `docker exec kafka` on the Connect host | Broker container is on the broker instance |

## Connectors

| Connector | Symptom | Fix |
|---|---|---|
| JDBC Sink | `requires … Struct … found HashMap` | `value.converter.schemas.enable=true`; upstream emits the schema envelope |
| Lambda bridge | `Unrecognized configs: api_version_auto_timeout_ms` | Remove that arg (not valid in kafka‑python 3.0.8) |
| Lambda bridge | Messages silently dropped by JDBC Sink | Wrap payload in `{"schema":…,"payload":…}` in the Lambda |
| S3 Sink | `JsonParseException: Unrecognized token 'hackathon'` | Old plain‑text test record; add `errors.tolerance=all` + `auto.offset.reset=latest` |
| Snowflake Sink | `NoClassDefFoundError: BouncyCastleFipsProvider` | Resolve full dependency tree (Maven `copy-dependencies`) |
| Snowflake Sink | Still missing `bcpkix-fips` | It's `provided`‑scope; add as an explicit dependency |
| Snowflake Sink | `UnsatisfiedLinkError: libgcc_s.so.1` / `__register_atfork` | Rebuild Connect on a glibc image (`Dockerfile.kafka-connect`) |
| Snowflake Sink | classic‑migration validation error | `snowflake.streaming.validate.compatibility.with.classic=false` |

## dbt

| Symptom | Cause | Fix |
|---|---|---|
| `dbt debug`: git not found | git not installed | `dnf install -y git` |
| YAML parse error near a description | Unquoted `Gold: …` (`: ` parsed as mapping) | Quote the description |
| `accepted_values` deprecation warning | New syntax nests args | Put values under `arguments:` |
| `invalid identifier 'TIMESTAMP'` | Reserved word referenced unquoted in test SQL | `quote: true` on that column |
| Gold "does not exist" | dbt materializes as `BRONZE_GOLD`, not `GOLD` | Target `IOT_PLATFORM.BRONZE_GOLD` |

### The `BRONZE_*` schema naming, explained

dbt's default `generate_schema_name` **concatenates** the connection's default
schema with each model's custom `+schema`. With default schema `BRONZE`
(from `profiles.yml`) and `+schema: gold`, the result is `BRONZE_GOLD` (and
`BRONZE_SILVER`, `BRONZE_BRONZE`). This is why the dashboard's role is granted
on, and the app reads from, `IOT_PLATFORM.BRONZE_GOLD`.

## Streamlit

| Symptom | Cause | Fix |
|---|---|---|
| "Not connected" / no data after running the SQL | Grants/config targeted `GOLD` instead of `BRONZE_GOLD` | Repoint to `BRONZE_GOLD` |
| Blank map tiles in a screenshot | Restricted outbound in the capture tool | Cosmetic; a real browser loads tiles |

## Phantom devices after the simulator outage

While the simulator was misconfigured (non‑static `device_id`), it produced
many one‑off device ids that persist in `gold_latest_device_status`, inflating
"Total Devices" until fresh data dilutes them. Not auto‑cleaned (it would mean
deleting production rows). Optionally delete those historical rows from
PostgreSQL/Bronze if an accurate count is needed immediately.
