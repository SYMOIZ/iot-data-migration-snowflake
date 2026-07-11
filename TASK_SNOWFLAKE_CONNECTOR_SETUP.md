# Task: Configure and Validate the Snowflake Kafka Connector

**Date:** 2026-07-11
**Scope:** Install the Snowflake Kafka Connector plugin, register `iot-snowflake-sink`
(`cdc.public.iot_events` → `IOT_PLATFORM.BRONZE.IOT_EVENTS_RAW`), and validate the complete
pipeline end-to-end. dbt Core not started, per instructions.

---

## Security Incident and Remediation (happened during this task)

While registering the connector, a bug in my own diagnostic redaction script printed the RSA
**private key** in plaintext into a command output. Full details and remediation already
committed and pushed in a prior turn:

1. Generated a brand-new RSA key pair immediately.
2. Updated the Secrets Manager secret (`iot-hackathon/snowflake/kafka-connector-key`) with the
   new private key.
3. Gave you the exact `ALTER USER ... SET RSA_PUBLIC_KEY=...` statement, which you ran in
   Snowsight.
4. Confirmed with you before proceeding further.

The connector below uses **only the new, rotated key** — the exposed key is retired and was never
put into active use for any authenticated connection.

---

## Plugin Installation — More Involved Than Expected

Installing `com.snowflake:snowflake-kafka-connector:4.0.2` took three attempts to get right,
each catching a real, distinct problem:

### 1. Missing transitive dependencies

The Maven Central artifact is not a shaded/fat JAR. Installing just the single JAR produced
`NoClassDefFoundError: org/bouncycastle/jcajce/provider/BouncyCastleFipsProvider` on connector
validation. Used a throwaway Maven Docker container (`mvn dependency:copy-dependencies`) to
resolve the full dependency tree instead of hand-tracking ~20 transitive JARs — safer and more
correct than guessing versions individually.

### 2. A `provided`-scope dependency Maven correctly excluded, but the runtime needed anyway

The first dependency resolution still didn't pull in the required BouncyCastle FIPS JARs
(`bcpkix-fips` and its own dependencies) — they're marked `<scope>provided</scope>` in the
connector's POM, meaning "the runtime environment should already have this," but Kafka Connect
doesn't. Added `bcpkix-fips` as an explicit direct dependency in the resolution project to pull
it (and its transitive deps) in.

### 3. Alpine/musl vs. glibc — required switching the Kafka Connect base image

Once the plugin loaded, the connector task failed with
`UnsatisfiedLinkError: ... Error loading shared library libgcc_s.so.1` — the Snowflake connector's
**native Snowpipe Streaming client** (a JNI library) is compiled against glibc, but
`apache/kafka:4.0.2` (used for the Kafka Connect worker since Task "Deploy Kafka Connect") is
Alpine-based (musl libc). Tried Alpine's `gcompat` compatibility shim first — got further, but
hit `Error relocating cyclone_shared.so: __register_atfork: symbol not found`, confirming gcompat
doesn't implement enough of the glibc ABI for this specific native library.

**Fix:** replaced the Kafka Connect image with a multi-stage build
(`infra/kafka/Dockerfile.kafka-connect`) that copies the same `/opt/kafka` installation from
`apache/kafka:4.0.2` onto `eclipse-temurin:17-jre` (genuinely glibc-based, Ubuntu). This only
changes the OS layer underneath — same Kafka/Connect binaries, same plugins (all four connectors'
JARs are stored in the persistent `kafka-connect-plugins` volume, unaffected by the image
rebuild), same configuration.

### 4. Config validation error (after the above fixes)

`SnowflakeStreamingSinkConnector.start()` rejected the config:
`snowflake.streaming.validate.compatibility.with.classic is enabled but ... is not explicitly set`
— a migration-compatibility check for accounts moving from the classic Snowpipe-based connector
(v3.x) to this streaming one (v4.x). Not applicable here since this is a brand-new deployment with
no prior connector version. Set `snowflake.streaming.validate.compatibility.with.classic=false`
to skip the check, which is the documented option for exactly this case.

All four fixes are reflected in the committed files (`infra/kafka/Dockerfile.kafka-connect`,
`infra/kafka/docker-compose.kafka-connect.yml`, `infra/kafka/connectors/iot-snowflake-sink.json`).

---

## Final Connector Configuration

```json
{
  "name": "iot-snowflake-sink",
  "config": {
    "connector.class": "com.snowflake.kafka.connector.SnowflakeStreamingSinkConnector",
    "tasks.max": "1",
    "topics": "cdc.public.iot_events",
    "snowflake.topic2table.map": "cdc.public.iot_events:IOT_EVENTS_RAW",
    "snowflake.url.name": "https://JCANAAG-YCB85704.snowflakecomputing.com:443",
    "snowflake.user.name": "KAFKA_CONNECTOR_USER",
    "snowflake.private.key": "<from Secrets Manager, rotated>",
    "snowflake.role.name": "KAFKA_CONNECTOR_ROLE",
    "snowflake.database.name": "IOT_PLATFORM",
    "snowflake.schema.name": "BRONZE",
    "snowflake.enable.schematization": "false",
    "snowflake.streaming.validate.compatibility.with.classic": "false",
    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter.schemas.enable": "false",
    "errors.tolerance": "all",
    "errors.log.enable": "true",
    "errors.log.include.messages": "true"
  }
}
```

Note: the connector class is `SnowflakeStreamingSinkConnector`, not the classic
`SnowflakeSinkConnector` drafted in the prior (not-yet-deployed) task — confirmed by checking the
actually-installed plugin list before registering, not assumed. `snowflake.enable.schematization`
is explicitly set `false` (its default is `true` in this version) to preserve the 2-column
`RECORD_METADATA`/`RECORD_CONTENT` Bronze table shape from Step 1, rather than letting the
connector auto-split the Debezium envelope into individual typed columns.

---

## Validation Results

| Check | Result |
|---|---|
| Connector status | ✅ `RUNNING` |
| Task status | ✅ `RUNNING` |
| No authentication errors | ✅ confirmed — task failures were config-validation and native-library issues (fixed above), never an auth rejection |
| Other 3 connectors unaffected | ✅ `iot-postgres-sink`, `iot-postgres-cdc`, `iot-s3-sink` all still `RUNNING` after the image rebuild (plugin/connector state lives in the persistent Docker volume and Kafka's internal topics, not the container itself) |
| New CDC event produced | ✅ `UPDATE iot_events SET battery=42.0, temperature=19.9 WHERE id=2` |
| Event reaches Kafka | ✅ consumed from `cdc.public.iot_events`: `{"id":2,...,"temperature":19.9,...,"battery":42.0}` |
| Record appears in Snowflake | ✅ see verification query below |

### Verification Query and Results

Run via `snowflake-connector-python` (RSA key-pair auth, `KAFKA_CONNECTOR_ROLE`) from an EC2
instance with proven internet access:

```sql
SELECT RECORD_CONTENT:after:id::int,
       RECORD_CONTENT:after:device_id::string,
       RECORD_CONTENT:after:temperature::float,
       RECORD_CONTENT:after:battery::float,
       RECORD_CONTENT:op::string
FROM IOT_EVENTS_RAW
ORDER BY RECORD_METADATA:CreateTime::string DESC
LIMIT 10;
```

```
ROW_COUNT: 7

(2, 'device-validation-002', 19.9, 42.0, 'u')   <- the update just made, op='u'
(5, 'device-s3-sink-001',    31.1, 80.0, 'c')
(1, 'device-validation-001', 33.3, 55.5, 'u')
(4, 'device-lambda-bridge-003', 31.1, 76.0, 'r')
(3, 'device-validation-003', 30.2, 95.0, 'r')
(2, 'device-validation-002', 27.1, 87.0, 'r')
(1, 'device-validation-001', 29.5, 91.0, 'r')
```

The top row (`id=2, temperature=19.9, battery=42.0, op='u'`) matches the `UPDATE` statement
exactly, confirming the full chain: **PostgreSQL → Debezium → Kafka CDC topic → Snowflake
Streaming Sink → `IOT_PLATFORM.BRONZE.IOT_EVENTS_RAW`.** The other 6 rows are Debezium's initial
table snapshot (`op='r'`) plus the earlier update from the Debezium validation task (`op='u'`) and
the S3-sink validation message (`op='c'`, a fresh insert) — all previously-verified data, now also
confirmed present in Snowflake.

---

## Files Changed/Added

- `infra/kafka/Dockerfile.kafka-connect` — new, the glibc-based custom image
- `infra/kafka/docker-compose.kafka-connect.yml` — updated to build from the Dockerfile
- `infra/kafka/connectors/iot-snowflake-sink.json` — final working config
- `infra/snowflake/step1_snowflake_setup.sql` — RSA key rotated (prior commit)

---

## Next Step

All four connectors (JDBC Sink, Debezium, S3 Sink, Snowflake Sink) are running and validated.
Bronze layer is live. Awaiting your approval before dbt Core. MSK cleanup remains outstanding,
untouched.
