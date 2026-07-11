#!/usr/bin/env python3
"""IoT device simulator for the hackathon pipeline.

Simulates N devices near the O2 Arena, London (51.5033 N, 0.0031 E) walking a
small random path and reporting GPS + sensor telemetry over MQTT to AWS IoT
Core, authenticated via SigV4/WebSocket using the caller's IAM credentials
(no device certificates, no hardcoded secrets).

IoT Core Rule 'iot_hackathon_to_kafka' subscribes to iot/+/telemetry and
republishes each message onto the MSK topic 'iot-events' via Lambda.

Usage:
    python3 simulator.py --devices 5 --interval 5 --duration 120
"""
import argparse
import json
import random
import threading
import time
from datetime import datetime, timezone

import boto3
from awscrt import mqtt, auth
from awsiot import mqtt_connection_builder

O2_ARENA_LAT = 51.5033
O2_ARENA_LON = 0.0031


def get_iot_endpoint(region: str) -> str:
    client = boto3.client("iot", region_name=region)
    resp = client.describe_endpoint(endpointType="iot:Data-ATS")
    return resp["endpointAddress"]


def build_connection(endpoint: str, region: str, client_id: str):
    credentials_provider = auth.AwsCredentialsProvider.new_default_chain()
    return mqtt_connection_builder.websockets_with_default_aws_signing(
        endpoint=endpoint,
        region=region,
        credentials_provider=credentials_provider,
        client_id=client_id,
        clean_session=True,
        keep_alive_secs=30,
    )


class SimulatedDevice:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.lat = O2_ARENA_LAT + random.uniform(-0.002, 0.002)
        self.lon = O2_ARENA_LON + random.uniform(-0.002, 0.002)
        self.battery = random.uniform(70, 100)

    def next_reading(self) -> dict:
        self.lat += random.uniform(-0.0004, 0.0004)
        self.lon += random.uniform(-0.0004, 0.0004)
        self.battery = max(0, self.battery - random.uniform(0, 0.05))
        return {
            "device_id": self.device_id,
            "event_time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "latitude": round(self.lat, 6),
            "longitude": round(self.lon, 6),
            "temperature_c": round(random.uniform(15, 28), 1),
            "humidity_pct": round(random.uniform(30, 70), 1),
            "battery_pct": round(self.battery, 1),
            "speed_kmh": round(random.uniform(0, 25), 1),
            "aqi": round(random.uniform(10, 90), 1),
        }


def run_device(connection, device: SimulatedDevice, interval: float, stop_event: threading.Event, stats: dict):
    topic = f"iot/{device.device_id}/telemetry"
    while not stop_event.is_set():
        payload = device.next_reading()
        connection.publish(
            topic=topic,
            payload=json.dumps(payload),
            qos=mqtt.QoS.AT_LEAST_ONCE,
        )
        stats[device.device_id] = stats.get(device.device_id, 0) + 1
        print(f"[{device.device_id}] published {payload['event_time']} lat={payload['latitude']} lon={payload['longitude']}")
        stop_event.wait(interval)


def main():
    parser = argparse.ArgumentParser(description="AWS IoT device simulator (GPS + telemetry)")
    parser.add_argument("--devices", type=int, default=5)
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between readings per device")
    parser.add_argument("--duration", type=float, default=0, help="seconds to run, 0 = until Ctrl+C")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--project", default="iot-hackathon")
    args = parser.parse_args()

    endpoint = get_iot_endpoint(args.region)
    print(f"IoT Core endpoint: {endpoint}")

    devices = [SimulatedDevice(f"{args.project}-device-{i:03d}") for i in range(1, args.devices + 1)]
    stop_event = threading.Event()
    stats: dict = {}
    threads = []

    connections = []
    for device in devices:
        conn = build_connection(endpoint, args.region, client_id=device.device_id)
        connect_future = conn.connect()
        connect_future.result(timeout=15)
        print(f"[{device.device_id}] connected")
        connections.append(conn)
        t = threading.Thread(target=run_device, args=(conn, device, args.interval, stop_event, stats), daemon=True)
        threads.append(t)
        t.start()

    try:
        if args.duration > 0:
            time.sleep(args.duration)
            stop_event.set()
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping simulator...")
        stop_event.set()
    finally:
        for t in threads:
            t.join(timeout=5)
        for conn in connections:
            conn.disconnect().result(timeout=10)
        total = sum(stats.values())
        print(f"Done. Published {total} messages across {len(devices)} devices: {stats}")


if __name__ == "__main__":
    main()
