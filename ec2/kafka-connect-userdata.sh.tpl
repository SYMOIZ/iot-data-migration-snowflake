#!/bin/bash
# Self-managed Kafka Connect worker (Docker Compose) for the IoT hackathon pipeline.
# Runs Debezium's Kafka Connect distribution + the Debezium JDBC Sink connector +
# the Debezium Postgres source connector (built-in) + (staged for Phase 2) the
# Snowflake Kafka Connector, authenticating to MSK with IAM (aws-msk-iam-auth).
#
# Templated by CDK (KafkaConnectStack). Idempotent: safe to re-run (e.g. on
# instance replace, or via SSM to pick up config changes).
set -euxo pipefail

exec > >(tee /var/log/iot-kafka-connect-bootstrap.log | logger -t iot-kafka-connect-bootstrap) 2>&1

AWS_REGION="{{AWS_REGION}}"
MSK_BOOTSTRAP_BROKERS="{{MSK_BOOTSTRAP_BROKERS}}"
DB_SECRET_ARN="{{DB_SECRET_ARN}}"
DB_NAME="{{DB_NAME}}"
POSTGRES_PRIVATE_IP="{{POSTGRES_PRIVATE_IP}}"
KAFKA_TOPIC="{{KAFKA_TOPIC}}"

DEBEZIUM_VERSION="3.6.0.Final"
POSTGRES_JDBC_VERSION="42.7.4"
MSK_IAM_AUTH_VERSION="2.3.7"
SNOWFLAKE_CONNECTOR_VERSION="4.0.2"
MAVEN_BASE="https://repo1.maven.org/maven2"
WORKDIR="/opt/kafka-connect"

dnf install -y docker jq awscli
systemctl enable docker
systemctl start docker

# docker compose v2 CLI plugin (not always in AL2023 base repos - fetch the static binary).
mkdir -p /usr/libexec/docker/cli-plugins
if [ ! -x /usr/libexec/docker/cli-plugins/docker-compose ]; then
  curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-$(uname -m)" \
    -o /usr/libexec/docker/cli-plugins/docker-compose
  chmod +x /usr/libexec/docker/cli-plugins/docker-compose
fi

# Note: containers reach the EC2 instance metadata service (needed for aws-msk-iam-auth
# and the AWS CLI default credential chain inside the container) through an extra
# network hop via the Docker bridge. IMDSv2's default hop limit of 1 would block that,
# so the instance is launched with http_put_response_hop_limit=2 (see KafkaConnectStack).

mkdir -p "$WORKDIR"/{extra-plugins/debezium-jdbc-sink,extra-plugins/snowflake-kafka-connector,extra-libs}
cd "$WORKDIR"

download() {
  local url="$1" out="$2"
  [ -f "$out" ] && { echo "already have $out"; return; }
  curl -fsSL --retry 3 --retry-delay 2 -o "$out" "$url"
}

# --- Debezium JDBC Sink connector (iot-events -> PostgreSQL) ---
if [ ! -f extra-plugins/debezium-jdbc-sink/.installed ]; then
  download "$MAVEN_BASE/io/debezium/debezium-connector-jdbc/${DEBEZIUM_VERSION}/debezium-connector-jdbc-${DEBEZIUM_VERSION}-plugin.tar.gz" /tmp/dbz-jdbc.tar.gz
  tar -xzf /tmp/dbz-jdbc.tar.gz -C extra-plugins/debezium-jdbc-sink --strip-components=1
  download "$MAVEN_BASE/org/postgresql/postgresql/${POSTGRES_JDBC_VERSION}/postgresql-${POSTGRES_JDBC_VERSION}.jar" extra-plugins/debezium-jdbc-sink/postgresql-${POSTGRES_JDBC_VERSION}.jar
  touch extra-plugins/debezium-jdbc-sink/.installed
fi

# --- Snowflake Kafka Connector (staged now, connector instance created in Phase 2
# once Snowflake credentials exist - see scripts/deploy-snowflake-connector.sh) ---
if [ ! -f extra-plugins/snowflake-kafka-connector/.installed ]; then
  download "$MAVEN_BASE/com/snowflake/snowflake-kafka-connector/${SNOWFLAKE_CONNECTOR_VERSION}/snowflake-kafka-connector-${SNOWFLAKE_CONNECTOR_VERSION}.jar" \
    extra-plugins/snowflake-kafka-connector/snowflake-kafka-connector-${SNOWFLAKE_CONNECTOR_VERSION}.jar
  touch extra-plugins/snowflake-kafka-connector/.installed
fi

# --- aws-msk-iam-auth: mounted onto the Connect worker's core classpath (/kafka/libs),
# not the isolated plugin path, since it's a SASL callback handler, not a connector. ---
download "$MAVEN_BASE/software/amazon/msk/aws-msk-iam-auth/${MSK_IAM_AUTH_VERSION}/aws-msk-iam-auth-${MSK_IAM_AUTH_VERSION}.jar" \
  extra-libs/aws-msk-iam-auth.jar

cat > docker-compose.yml <<COMPOSE
services:
  kafka-connect:
    image: debezium/connect:2.7
    restart: unless-stopped
    network_mode: bridge
    ports:
      - "8083:8083"
    environment:
      BOOTSTRAP_SERVERS: "${MSK_BOOTSTRAP_BROKERS}"
      GROUP_ID: iot-hackathon-connect
      CONFIG_STORAGE_TOPIC: iot-hackathon-connect-configs
      OFFSET_STORAGE_TOPIC: iot-hackathon-connect-offsets
      STATUS_STORAGE_TOPIC: iot-hackathon-connect-status
      KEY_CONVERTER: org.apache.kafka.connect.json.JsonConverter
      VALUE_CONVERTER: org.apache.kafka.connect.json.JsonConverter
      CONNECT_KEY_CONVERTER_SCHEMAS_ENABLE: "false"
      CONNECT_VALUE_CONVERTER_SCHEMAS_ENABLE: "false"
      CONNECT_PLUGIN_PATH: /kafka/connect,/extra-plugins
      CONNECT_SECURITY_PROTOCOL: SASL_SSL
      CONNECT_SASL_MECHANISM: AWS_MSK_IAM
      CONNECT_SASL_JAAS_CONFIG: software.amazon.msk.auth.iam.IAMLoginModule required;
      CONNECT_SASL_CLIENT_CALLBACK_HANDLER_CLASS: software.amazon.msk.auth.iam.IAMClientCallbackHandler
      CONNECT_PRODUCER_SECURITY_PROTOCOL: SASL_SSL
      CONNECT_PRODUCER_SASL_MECHANISM: AWS_MSK_IAM
      CONNECT_PRODUCER_SASL_JAAS_CONFIG: software.amazon.msk.auth.iam.IAMLoginModule required;
      CONNECT_PRODUCER_SASL_CLIENT_CALLBACK_HANDLER_CLASS: software.amazon.msk.auth.iam.IAMClientCallbackHandler
      CONNECT_CONSUMER_SECURITY_PROTOCOL: SASL_SSL
      CONNECT_CONSUMER_SASL_MECHANISM: AWS_MSK_IAM
      CONNECT_CONSUMER_SASL_JAAS_CONFIG: software.amazon.msk.auth.iam.IAMLoginModule required;
      CONNECT_CONSUMER_SASL_CLIENT_CALLBACK_HANDLER_CLASS: software.amazon.msk.auth.iam.IAMClientCallbackHandler
      AWS_REGION: "${AWS_REGION}"
    volumes:
      - ${WORKDIR}/extra-plugins:/extra-plugins:ro
      - ${WORKDIR}/extra-libs/aws-msk-iam-auth.jar:/kafka/libs/aws-msk-iam-auth.jar:ro
COMPOSE

docker compose up -d

echo "Waiting for Kafka Connect REST API..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8083/ >/dev/null; then echo "Connect is up"; break; fi
  sleep 5
done

# --- Create the iot-events topic (idempotent) ---
cat > /tmp/client.properties <<'PROPS'
security.protocol=SASL_SSL
sasl.mechanism=AWS_MSK_IAM
sasl.jaas.config=software.amazon.msk.auth.iam.IAMLoginModule required;
sasl.client.callback.handler.class=software.amazon.msk.auth.iam.IAMClientCallbackHandler
PROPS
docker cp /tmp/client.properties "$(docker compose ps -q kafka-connect)":/tmp/client.properties

EXISTING_TOPICS=$(docker compose exec -T kafka-connect /kafka/bin/kafka-topics.sh \
  --bootstrap-server "$MSK_BOOTSTRAP_BROKERS" --command-config /tmp/client.properties --list || true)
if ! echo "$EXISTING_TOPICS" | grep -qx "$KAFKA_TOPIC"; then
  docker compose exec -T kafka-connect /kafka/bin/kafka-topics.sh \
    --bootstrap-server "$MSK_BOOTSTRAP_BROKERS" --command-config /tmp/client.properties \
    --create --topic "$KAFKA_TOPIC" --partitions 3 --replication-factor 2
fi

# --- Register the JDBC sink connector (iot-events -> PostgreSQL.iot_events), idempotent PUT ---
# xtrace disabled from here on: `set -x` echoes the expanded value of assignment
# statements, which would otherwise leak the DB password into the bootstrap log.
set +x
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "$DB_SECRET_ARN" --region "$AWS_REGION" --query SecretString --output text)
DB_USER=$(echo "$SECRET_JSON" | jq -r .username)
DB_PASS=$(echo "$SECRET_JSON" | jq -r .password)

for i in $(seq 1 30); do
  if curl -sf http://localhost:8083/connector-plugins >/dev/null; then break; fi
  sleep 5
done

curl -s -X PUT http://localhost:8083/connectors/iot-hackathon-jdbc-sink/config \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "connector.class": "io.debezium.connector.jdbc.JdbcSinkConnector",
  "tasks.max": "1",
  "topics": "${KAFKA_TOPIC}",
  "connection.url": "jdbc:postgresql://${POSTGRES_PRIVATE_IP}:5432/${DB_NAME}",
  "connection.username": "${DB_USER}",
  "connection.password": "${DB_PASS}",
  "insert.mode": "upsert",
  "primary.key.mode": "record_value",
  "primary.key.fields": "device_id,event_time",
  "table.name.format": "iot_events",
  "schema.evolution": "basic",
  "delete.enabled": "false",
  "database.time_zone": "UTC"
}
JSON

echo "iot-kafka-connect-bootstrap complete" > /var/log/iot-kafka-connect-bootstrap.done
