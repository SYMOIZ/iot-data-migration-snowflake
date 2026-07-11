#!/bin/bash
# PostgreSQL "on-prem simulation" bootstrap for the IoT hackathon pipeline.
# Templated by CDK (DatabaseStack) - {{DB_SECRET_ARN}}, {{AWS_REGION}}, {{DB_NAME}}, {{VPC_CIDR}}
# are substituted at synth time. Idempotent: safe to re-run (e.g. on instance replace).
set -euxo pipefail

exec > >(tee /var/log/iot-postgres-bootstrap.log | logger -t iot-postgres-bootstrap) 2>&1

DB_SECRET_ARN="{{DB_SECRET_ARN}}"
AWS_REGION="{{AWS_REGION}}"
DB_NAME="{{DB_NAME}}"
VPC_CIDR="{{VPC_CIDR}}"
PG_VERSION="15"
PGDATA="/var/lib/pgsql/${PG_VERSION}/data"
SERVICE="postgresql-${PG_VERSION}"

dnf install -y postgresql${PG_VERSION} postgresql${PG_VERSION}-server postgresql${PG_VERSION}-contrib jq awscli amazon-cloudwatch-agent

if [ ! -f "${PGDATA}/PG_VERSION" ]; then
  /usr/bin/postgresql-${PG_VERSION}-setup initdb
fi

systemctl enable "${SERVICE}"
systemctl start "${SERVICE}"

# Pull credentials from Secrets Manager (never hardcoded). xtrace is disabled from
# here on: `set -x` echoes the expanded value of assignment statements, which would
# otherwise leak the password into /var/log/iot-postgres-bootstrap.log.
set +x
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "${DB_SECRET_ARN}" --region "${AWS_REGION}" --query SecretString --output text)
DB_USER=$(echo "${SECRET_JSON}" | jq -r .username)
DB_PASS=$(echo "${SECRET_JSON}" | jq -r .password)

# --- postgresql.conf: enable logical WAL for Debezium CDC (Phase 2) ---
CONF="${PGDATA}/postgresql.conf"
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "${CONF}"
sed -i "s/^#\?wal_level.*/wal_level = logical/" "${CONF}"
sed -i "s/^#\?max_wal_senders.*/max_wal_senders = 10/" "${CONF}"
sed -i "s/^#\?max_replication_slots.*/max_replication_slots = 10/" "${CONF}"
grep -q "^wal_level" "${CONF}" || echo "wal_level = logical" >> "${CONF}"
grep -q "^max_wal_senders" "${CONF}" || echo "max_wal_senders = 10" >> "${CONF}"
grep -q "^max_replication_slots" "${CONF}" || echo "max_replication_slots = 10" >> "${CONF}"

# --- pg_hba.conf: allow scram-sha-256 auth from the VPC (Kafka Connect, Debezium, bastion) ---
HBA="${PGDATA}/pg_hba.conf"
if ! grep -q "iot-hackathon-vpc-access" "${HBA}"; then
  echo "host all all ${VPC_CIDR} scram-sha-256 # iot-hackathon-vpc-access" >> "${HBA}"
  echo "host replication all ${VPC_CIDR} scram-sha-256 # iot-hackathon-vpc-access" >> "${HBA}"
fi
sed -i "s/^password_encryption.*/password_encryption = scram-sha-256/" "${CONF}" || true
grep -q "^password_encryption" "${CONF}" || echo "password_encryption = scram-sha-256" >> "${CONF}"

systemctl restart "${SERVICE}"
until sudo -u postgres psql -c '\q' 2>/dev/null; do sleep 2; done

# --- Create role, database, schema, tables (idempotent) ---
sudo -u postgres psql -v ON_ERROR_STOP=0 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}' REPLICATION;
  ELSE
    ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASS}' REPLICATION;
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

sudo -u postgres psql -d "${DB_NAME}" -v ON_ERROR_STOP=1 <<SQL
CREATE TABLE IF NOT EXISTS iot_events (
    id            BIGSERIAL PRIMARY KEY,
    device_id     VARCHAR(64)      NOT NULL,
    event_time    TIMESTAMPTZ      NOT NULL,
    latitude      DOUBLE PRECISION NOT NULL,
    longitude     DOUBLE PRECISION NOT NULL,
    temperature_c DOUBLE PRECISION,
    humidity_pct  DOUBLE PRECISION,
    battery_pct   DOUBLE PRECISION,
    speed_kmh     DOUBLE PRECISION,
    aqi           DOUBLE PRECISION,
    ingested_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),
    UNIQUE (device_id, event_time)
);
CREATE INDEX IF NOT EXISTS idx_iot_events_device_time ON iot_events (device_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_iot_events_event_time ON iot_events (event_time DESC);

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${DB_USER};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${DB_USER};

CREATE PUBLICATION IF NOT EXISTS dbz_publication FOR TABLE iot_events;
SQL

# CloudWatch agent: ship postgres + system logs/metrics (best-effort, non-fatal).
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CWCFG'
{
  "metrics": {"append_dimensions": {"InstanceId": "${aws:InstanceId}"}, "metrics_collected": {"mem": {"measurement": ["mem_used_percent"]}, "disk": {"measurement": ["used_percent"], "resources": ["/"]}}},
  "logs": {"logs_collected": {"files": {"collect_list": [{"file_path": "/var/log/iot-postgres-bootstrap.log", "log_group_name": "/iot-hackathon/postgres/bootstrap", "log_stream_name": "{instance_id}"}]}}}
}
CWCFG
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s || true

echo "iot-postgres-bootstrap complete" > /var/log/iot-postgres-bootstrap.done
