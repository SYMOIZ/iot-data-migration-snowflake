import json
import logging
import os
from datetime import datetime, timezone

from kafka import KafkaProducer

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BOOTSTRAP_SERVERS = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
TOPIC = os.environ["KAFKA_TOPIC"]

# Matches the schema the downstream JDBC Sink connector (iot-postgres-sink) expects:
# pk.mode=none requires a proper Struct, not a raw/schemaless JSON map, so this Lambda
# wraps every event in Kafka Connect's standard {"schema": ..., "payload": ...} envelope
# rather than forwarding the flat IoT Core payload as-is.
_SCHEMA = {
    "type": "struct",
    "optional": False,
    "name": "iot_event",
    "fields": [
        {"field": "device_id", "type": "string"},
        {
            "field": "timestamp",
            "type": "int64",
            "name": "org.apache.kafka.connect.data.Timestamp",
            "version": 1,
        },
        {"field": "latitude", "type": "double"},
        {"field": "longitude", "type": "double"},
        {"field": "temperature", "type": "double"},
        {"field": "humidity", "type": "double"},
        {"field": "heart_rate", "type": "double"},
        {"field": "battery", "type": "double"},
    ],
}

_producer = None


def _get_producer():
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            security_protocol="PLAINTEXT",
            request_timeout_ms=10000,
        )
    return _producer


def _to_epoch_millis(value):
    if isinstance(value, (int, float)):
        # Already numeric - assume epoch millis if large, else epoch seconds.
        return int(value) if value > 10**12 else int(value * 1000)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _build_envelope(event):
    payload = {
        "device_id": str(event["device_id"]),
        "timestamp": _to_epoch_millis(event["timestamp"]),
        "latitude": float(event["latitude"]),
        "longitude": float(event["longitude"]),
        "temperature": float(event["temperature"]),
        "humidity": float(event["humidity"]),
        "heart_rate": float(event["heart_rate"]),
        "battery": float(event["battery"]),
    }
    return {"schema": _SCHEMA, "payload": payload}


def handler(event, context):
    logger.info("Received IoT Core event: %s", json.dumps(event)[:2000])

    envelope = _build_envelope(event)
    producer = _get_producer()
    future = producer.send(TOPIC, value=envelope)
    record_metadata = future.get(timeout=10)

    logger.info(
        "Published to Kafka topic=%s partition=%s offset=%s",
        record_metadata.topic,
        record_metadata.partition,
        record_metadata.offset,
    )

    return {
        "status": "ok",
        "topic": record_metadata.topic,
        "partition": record_metadata.partition,
        "offset": record_metadata.offset,
    }
