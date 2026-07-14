# End‑to‑End Validation

Use this to confirm each stage works, and to prove the full pipeline
end‑to‑end. Work top‑to‑bottom; each check assumes the previous stages pass.

---

## Per‑stage checks

| Stage | How to verify |
|---|---|
| Network | All 5 VPC endpoints **Available**; instances register **Online** in SSM Fleet Manager |
| Security | S3 bucket exists (public access blocked); DB secret retrievable |
| Device Simulator | Simulation **Running**; MQTT test client shows 5 devices on `iot-events` with stable `device_id` |
| IoT Core | Test publish appears in `/aws/iotrule/iot-hackathon-iot-events` |
| PostgreSQL | `systemctl is-active postgresql`=active; `SHOW wal_level`=logical; table exists |
| Kafka broker | `docker ps` shows kafka Up; both topics healthy; produce/consume round‑trip |
| Kafka Connect | `GET /` returns version; `kafka_cluster_id` matches the broker |
| Lambda bridge | Lambda logs show `Published to Kafka …`; message on `iot-events` |
| JDBC Sink | Connector RUNNING; rows in `iot_platform.iot_events` |
| S3 Sink | Connector RUNNING; JSON object under `raw/iot-events/year=…/` |
| Debezium | Slot `debezium` active; update produces `op:"u"` on `cdc.public.iot_events` |
| Snowflake Sink | Connector RUNNING; new row in `BRONZE.IOT_EVENTS_RAW` |
| dbt | `dbt run` all models pass; `dbt test` all pass |
| Streamlit | Sidebar **Connected**; all pages render live Gold data |

---

## Full pipeline smoke test

1. Ensure the simulator is **Running**.
2. Watch the message move through:
   - Kafka `iot-events` offsets increase (broker `kafka-get-offsets.sh`).
   - New rows in PostgreSQL `iot_platform.iot_events`.
   - New object in the S3 `raw/` prefix.
   - Debezium emits to `cdc.public.iot_events`.
   - `BRONZE.IOT_EVENTS_RAW` row count grows.
3. Trigger a `dbt run` (or wait for the 5‑minute cron), then refresh the
   dashboard — the new data appears in the Gold KPIs.

**Checking Snowflake / Kafka from your own machine:** the broker and Snowflake
aren't publicly reachable. Run Kafka checks from the broker via SSM, and run
Snowflake queries from an EC2 instance that has outbound internet through the
NAT gateway.

## Confirming data actually flows (not just "services up")

The most useful single indicator is the **Bronze row count over time** — if it
grows while the simulator runs, the entire IoT → IoT Core → Lambda → Kafka →
Debezium → Snowflake chain is healthy:

```sql
SELECT COUNT(*),
       MAX(RECORD_METADATA:CreateTime::number) AS latest_ms
FROM IOT_PLATFORM.BRONZE.IOT_EVENTS_RAW;
```

If it's flat while the simulator "runs," start with
[troubleshooting.md](./troubleshooting.md) → *simulator produces no data*.

---

## Teardown

Delete stacks in **reverse** dependency order (Streamlit → dbt role → Snowflake
objects → connectors → Connect → broker → Lambda → database → simulator), then
the foundation. Remember the always‑on costs (NAT gateway, VPC interface
endpoints, EC2, the S3 bucket). Snowflake objects are dropped in Snowsight; the
warehouse auto‑suspends but still bills while resumed.
