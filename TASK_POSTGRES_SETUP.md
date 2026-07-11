# Task: Deploy PostgreSQL Server

**Date:** 2026-07-11
**Scope:** Create the `iot_platform` database and `iot_events` table for future Debezium CDC.
**No new EC2 instance was created** — see decision below. Kafka Connect, JDBC Sink, Debezium, and
Snowflake were not touched.

---

## Decision: Reused Existing PostgreSQL Instance (not a new EC2)

Before deploying anything, I checked current infrastructure and found PostgreSQL **already
running** on `i-08633055f8bc44815` (t3.large, from the `IotHackathon-Database` stack deployed
earlier), with `wal_level=logical` already configured — exactly the "future logical replication"
requirement. Deploying a second dedicated EC2 would have created a redundant ~$63/month
PostgreSQL server. Flagged this to you and you confirmed: reuse the existing instance.

| Requirement | Status on existing instance |
|---|---|
| Amazon Linux 2023, t3.large | ✅ already this spec |
| Existing VPC, existing security groups | ✅ already using `PostgresSg` |
| SSM configured, no public SSH | ✅ already the case |
| PostgreSQL 16 | ✅ version 16.14 running |
| Service enabled + running | ✅ `active`/`enabled` |
| WAL enabled for logical replication | ✅ `wal_level=logical` (already set) |

What was genuinely new work: the `iot_platform` database and `iot_events` table didn't exist yet
(the instance's existing database, from the original `IotHackathon-Security` secret, is named
`iot` — a different database, left untouched).

---

## Resources Created

| Resource | Detail |
|---|---|
| PostgreSQL role | `iot_platform_app` — `LOGIN`, `REPLICATION` (needed for future Debezium) |
| PostgreSQL database | `iot_platform`, owned by `iot_platform_app` |
| PostgreSQL table | `public.iot_events`, owned by `iot_platform_app` |
| Secrets Manager secret | `iot-hackathon/postgres/iot_platform-credentials` (new secret — the existing `IotHackathon-Security` secret was not modified, per the rule against touching reused-foundation resources) |

### Table Schema

```
                                       Table "public.iot_events"
   Column    |           Type           | Nullable |                Default
-------------+--------------------------+----------+-----------------------------------------
 id          | bigint                   | not null | nextval('iot_events_id_seq'::regclass)
 device_id   | character varying(64)    | not null |
 timestamp   | timestamp with time zone | not null |
 latitude    | double precision         |          |
 longitude   | double precision         |          |
 temperature | double precision         |          |
 humidity    | double precision         |          |
 heart_rate  | double precision         |          |
 battery     | double precision         |          |
Indexes:
    "iot_events_pkey" PRIMARY KEY, btree (id)
```

`id BIGSERIAL PRIMARY KEY` was added beyond your listed columns — Debezium strongly prefers (and
in most configurations requires) a primary key to correctly extract change-event keys for logical
replication, which is the explicit purpose of this table. Flagging this addition for visibility.

---

## Security Issue Found and Fixed

The setup script used `sudo -u postgres psql -v dbpass=$DB_PASS ...` to pass the new role's
password as a command-line argument. I intended to suppress bash's command tracing (`set -x`)
around this, but only suppressed it for the *variable assignment* line — tracing was back on for
the actual `psql` invocation, which **echoed the plaintext password into
`/var/log/iot-platform-db-setup.log`** on the instance (and into a tool result I retrieved in this
session).

**Remediation, done immediately:**
1. Generated a new 32-character random password.
2. Updated the Secrets Manager secret (`iot-hackathon/postgres/iot_platform-credentials`) with the new value.
3. Ran `ALTER ROLE iot_platform_app WITH PASSWORD '...'` using a corrected script — password embedded directly in the SQL heredoc body (never on a traced command line or argv) — to match the rotated secret.
4. Redacted the exposed password out of `/var/log/iot-platform-db-setup.log` on the instance (`dbpass=***REDACTED***`).
5. Verified the redaction and that the rotation succeeded.

The password currently in Secrets Manager is the only valid one; the originally-exposed value was
rotated out and is no longer active. No other credential (the existing `iot` database's secret,
or any other project secret) was touched or exposed.

---

## Validation Results

| Check | Result |
|---|---|
| PostgreSQL service running | ✅ `systemctl is-active postgresql` → `active`, `is-enabled` → `enabled` |
| Database exists | ✅ `iot_platform` present alongside pre-existing `postgres`/`iot` |
| Table exists with correct schema | ✅ `\d iot_events` — all 8 requested columns present with reasonable types, plus the primary key |
| WAL / logical replication ready | ✅ `wal_level=logical`; role has `REPLICATION` attribute |
| Credentials in Secrets Manager | ✅ `iot-hackathon/postgres/iot_platform-credentials`, rotated to a fresh, never-logged value |
| SSM connectivity | ✅ All of the above executed and confirmed via SSM Run Command — no SSH used at any point |

---

## Next Step

`iot_platform.iot_events` is ready to receive data and ready for Debezium CDC once that phase is
approved. Awaiting your approval before: JDBC Sink connector, Debezium connector, or Snowflake
integration. MSK cleanup also remains outstanding, untouched.
