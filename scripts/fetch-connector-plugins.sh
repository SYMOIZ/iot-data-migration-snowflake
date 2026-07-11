#!/usr/bin/env bash
# Downloads open-source Kafka Connect plugins from Maven Central and packages them
# as MSK Connect custom-plugin ZIPs under cdk/assets/plugins/.
#
# Confluent Hub (packages.confluent.io) and GitHub release assets are not reachable
# from this environment's egress policy, so we use the Debezium project's own
# connectors, both published to Maven Central under io.debezium:
#   - debezium-connector-postgres  -> CDC source connector (Phase 2)
#   - debezium-connector-jdbc      -> generic JDBC sink connector (Phase 1),
#     used in place of Confluent's kafka-connect-jdbc.
#
# Idempotent: re-running skips work that's already done unless FORCE=1.
set -euo pipefail

DEBEZIUM_VERSION="${DEBEZIUM_VERSION:-3.6.0.Final}"
POSTGRES_JDBC_VERSION="${POSTGRES_JDBC_VERSION:-42.7.4}"
MAVEN_BASE="https://repo1.maven.org/maven2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ASSETS_DIR="$ROOT_DIR/cdk/assets/plugins"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

mkdir -p "$ASSETS_DIR/jdbc-sink" "$ASSETS_DIR/debezium-postgres"

log() { echo "[fetch-connector-plugins] $*"; }

download() {
  local url="$1" out="$2"
  if [[ -f "$out" && "${FORCE:-0}" != "1" ]]; then
    log "already have $(basename "$out"), skipping"
    return
  fi
  log "downloading $url"
  curl -fsSL --retry 3 --retry-delay 2 -o "$out" "$url"
}

# --- Debezium Postgres source connector (Phase 2 CDC) ---
DBZ_PG_TARBALL="$WORK_DIR/debezium-connector-postgres-plugin.tar.gz"
download "$MAVEN_BASE/io/debezium/debezium-connector-postgres/${DEBEZIUM_VERSION}/debezium-connector-postgres-${DEBEZIUM_VERSION}-plugin.tar.gz" "$DBZ_PG_TARBALL"

if [[ ! -f "$ASSETS_DIR/debezium-postgres/plugin.zip" || "${FORCE:-0}" == "1" ]]; then
  log "packaging debezium-postgres plugin.zip"
  EXTRACT_DIR="$WORK_DIR/dbz-pg-extract"
  mkdir -p "$EXTRACT_DIR"
  tar -xzf "$DBZ_PG_TARBALL" -C "$EXTRACT_DIR"
  PLUGIN_SUBDIR="$(find "$EXTRACT_DIR" -maxdepth 1 -type d -name 'debezium-connector-postgres*' | head -1)"
  rm -f "$ASSETS_DIR/debezium-postgres/plugin.zip"
  (cd "$PLUGIN_SUBDIR" && zip -qr "$ASSETS_DIR/debezium-postgres/plugin.zip" .)
  log "wrote $ASSETS_DIR/debezium-postgres/plugin.zip"
fi

# --- Debezium JDBC sink connector (Phase 1: iot-events -> PostgreSQL) ---
DBZ_JDBC_TARBALL="$WORK_DIR/debezium-connector-jdbc-plugin.tar.gz"
download "$MAVEN_BASE/io/debezium/debezium-connector-jdbc/${DEBEZIUM_VERSION}/debezium-connector-jdbc-${DEBEZIUM_VERSION}-plugin.tar.gz" "$DBZ_JDBC_TARBALL"

PG_DRIVER_JAR="$WORK_DIR/postgresql-${POSTGRES_JDBC_VERSION}.jar"
download "$MAVEN_BASE/org/postgresql/postgresql/${POSTGRES_JDBC_VERSION}/postgresql-${POSTGRES_JDBC_VERSION}.jar" "$PG_DRIVER_JAR"

if [[ ! -f "$ASSETS_DIR/jdbc-sink/plugin.zip" || "${FORCE:-0}" == "1" ]]; then
  log "packaging jdbc-sink plugin.zip (Debezium JDBC sink + PostgreSQL driver)"
  EXTRACT_DIR="$WORK_DIR/dbz-jdbc-extract"
  mkdir -p "$EXTRACT_DIR"
  tar -xzf "$DBZ_JDBC_TARBALL" -C "$EXTRACT_DIR"
  PLUGIN_SUBDIR="$(find "$EXTRACT_DIR" -maxdepth 1 -type d -name 'debezium-connector-jdbc*' | head -1)"
  cp "$PG_DRIVER_JAR" "$PLUGIN_SUBDIR/"
  rm -f "$ASSETS_DIR/jdbc-sink/plugin.zip"
  (cd "$PLUGIN_SUBDIR" && zip -qr "$ASSETS_DIR/jdbc-sink/plugin.zip" .)
  log "wrote $ASSETS_DIR/jdbc-sink/plugin.zip"
fi

rm -f "$ASSETS_DIR/jdbc-sink/.gitkeep" "$ASSETS_DIR/debezium-postgres/.gitkeep"
log "done."
