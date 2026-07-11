"""IoT Core Rule target: republishes device telemetry from AWS IoT Core (MQTT) onto
the MSK topic 'iot-events', authenticating to the cluster with IAM (no Kafka
username/password to manage or leak). Uses kafka-python's native AWS_MSK_IAM sasl
mechanism, which signs with the Lambda execution role's credentials via botocore
(already present in the standard Lambda Python runtime).
"""
import json
import logging
import os

from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BOOTSTRAP_SERVERS = os.environ["MSK_BOOTSTRAP_SERVERS"]
TOPIC = os.environ.get("KAFKA_TOPIC", "iot-events")

_producer = None


def _get_producer() -> KafkaProducer:
    global _producer
    if _producer is None:
        logger.info("Creating KafkaProducer for %s", BOOTSTRAP_SERVERS)
        _producer = KafkaProducer(
            bootstrap_servers=BOOTSTRAP_SERVERS.split(","),
            security_protocol="SASL_SSL",
            sasl_mechanism="AWS_MSK_IAM",
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            retries=3,
            request_timeout_ms=15000,
            api_version=(2, 8, 0),
        )
    return _producer


def handler(event, context):
    """event is the raw JSON payload published by a device to iot/<device_id>/telemetry."""
    logger.info("Received IoT event: %s", json.dumps(event)[:1000])

    device_id = event.get("device_id", "unknown")
    try:
        producer = _get_producer()
        future = producer.send(TOPIC, key=device_id, value=event)
        future.get(timeout=10)
        producer.flush(timeout=10)
    except KafkaError:
        logger.exception("Failed to publish to Kafka topic %s", TOPIC)
        raise

    return {"status": "ok", "device_id": device_id, "topic": TOPIC}
