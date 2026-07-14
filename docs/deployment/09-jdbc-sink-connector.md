# 09 · JDBC Sink Connector (Kafka → PostgreSQL)

**Connector:** `iot-postgres-sink` · **Purpose:** write every `iot-events`
message into `iot_platform.iot_events` in PostgreSQL.

**Config file:** `infra/kafka/connectors/iot-postgres-sink.json`

Kafka Connect has no AWS Management Console — you administer it through its
REST API on port `8083`, which you reach from the **Bastion** Session Manager
shell (the Bastion SG is allowed to call `8083`).

---

## Step 1 — Install the plugin

From the Kafka Connect Session Manager shell, download the **Confluent JDBC
Sink Connector v10.9.6** from Confluent Hub, verify its MD5 against the
published checksum, and extract it into the persistent
`/opt/kafka-connect/plugins` volume (it bundles the PostgreSQL JDBC driver).
Restart the worker and confirm:

```bash
curl -s http://localhost:8083/connector-plugins | grep JdbcSinkConnector
```

## Step 2 — Register the connector

From the Bastion shell (which can reach the Connect REST API), POST the config.
The committed file uses a Secrets Manager **reference** for the password, not a
literal:

```json
{
  "name": "iot-postgres-sink",
  "config": {
    "connector.class": "io.confluent.connect.jdbc.JdbcSinkConnector",
    "tasks.max": "1",
    "topics": "iot-events",
    "connection.url": "jdbc:postgresql://<POSTGRES_PRIVATE_IP>:5432/iot_platform",
    "connection.user": "iot_platform_app",
    "connection.password": "${secretsManager:iot-hackathon/postgres/iot_platform-credentials:password}",
    "table.name.format": "iot_events",
    "insert.mode": "insert",
    "auto.create": "false",
    "auto.evolve": "false",
    "pk.mode": "none",
    "errors.tolerance": "all",
    "errors.log.enable": "true",
    "errors.log.include.messages": "true",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "true"
  }
}
```

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  --data @iot-postgres-sink.json http://<KAFKA_CONNECT_PRIVATE_IP>:8083/connectors
```

**Why `table.name.format`:** the topic is `iot-events` (hyphen) but the table
is `iot_events` (underscore); without this the connector looks for a table
that doesn't exist. **Why `value.converter.schemas.enable=true`:** with
`pk.mode=none` the sink needs a real `Struct`, which is why the Lambda bridge
emits the schema envelope.

---

## Verification

```bash
curl -s http://<KAFKA_CONNECT_PRIVATE_IP>:8083/connectors/iot-postgres-sink/status
# connector + task both "RUNNING"
```

From the Bastion, query PostgreSQL — new device rows appear in
`iot_platform.iot_events`.

---

## Issues encountered & fixes

1. **Schemaless records rejected.** `pk.mode=none` requires a `Struct`, but
   schemaless JSON parses as a `HashMap`. **Fix:** set this connector's
   `value.converter.schemas.enable=true` and have upstream emit the
   `{"schema": …, "payload": …}` envelope (handled by the Lambda bridge).
2. **Wrong instance for `docker exec`.** Publishing test messages, `docker exec
   kafka …` was run on the Connect host, which has no `kafka` container. **Fix:**
   run broker commands on the broker instance.
3. **Password visible via the REST API (known limitation).** Kafka Connect's
   REST API returns the full connector config, including any literal password.
   Using a `${secretsManager:…}` reference (as above, via the Secrets Manager
   config provider) is the correct mitigation; network access to `8083` is also
   restricted to the Bastion/client SGs.

---

Next: [10 · S3 Sink Connector](./10-s3-sink-connector.md)
