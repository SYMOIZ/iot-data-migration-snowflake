# 05 · PostgreSQL & Bastion (Database Infrastructure)

**Stack:** `IotHackathon-Database` · **Purpose:** the PostgreSQL "operational"
database that receives IoT events and is later the source for Debezium CDC,
plus a Bastion host (which is reused later as the dbt execution host).

**IaC reference:** `infra/database/` (CDK). It imports the network/security
foundation and creates only new resources.

---

## What to create

| Resource | Value |
|---|---|
| PostgreSQL EC2 | `t3.large`, Amazon Linux 2023, **private** subnet, no public IP |
| Bastion EC2 | `t3.micro`, Amazon Linux 2023, private subnet, no public IP |
| IAM role (Postgres) | `AmazonSSMManagedInstanceCore` + `GetSecretValue` on the DB secret only |
| IAM role (Bastion) | `AmazonSSMManagedInstanceCore` only |
| EBS data volume | 30 GiB gp3, encrypted, mounted at `/var/lib/pgsql` |
| PostgreSQL objects | database `iot_platform`, role `iot_platform_app`, table `public.iot_events` |
| Secret | `iot-hackathon/postgres/iot_platform-credentials` |

---

## Console steps

### Launch the instances

1. **EC2 → Instances → Launch instance** (do this twice — Postgres then
   Bastion):
   - AMI: **Amazon Linux 2023**; type `t3.large` (Postgres) / `t3.micro`
     (Bastion).
   - **Key pair: "Proceed without a key pair"** (SSM only).
   - Network: the project VPC, a **private subnet**, **Auto‑assign public IP =
     Disable**, security group `<POSTGRES_SG_ID>` (Postgres) /
     `<BASTION_SG_ID>` (Bastion).
   - **Advanced → IAM instance profile:** a role with
     `AmazonSSMManagedInstanceCore` (Postgres role also needs read on the DB
     secret).
   - Postgres only: add a **second EBS volume**, 30 GiB gp3, **Encrypted**.
2. Wait until both instances register **Online** in **Systems Manager → Fleet
   Manager**.

### Configure PostgreSQL (via SSM Session Manager)

**EC2 → select the Postgres instance → Connect → Session Manager → Connect.**
In that shell:

1. Install and initialize PostgreSQL 16, mounting the dedicated volume at
   `/var/lib/pgsql` before `initdb` so the data directory lives on it.
2. Set logical replication in `postgresql.conf` (required for Debezium later):

   ```
   wal_level = logical
   max_wal_senders = 10
   max_replication_slots = 10
   listen_addresses = '*'
   ```

3. In `pg_hba.conf`, allow `host` and `host replication` from the VPC CIDR
   `10.42.0.0/16` using `scram-sha-256`.
4. Create the application database and role, and the target table. Fetch the
   password from Secrets Manager at runtime — never hard‑code it:

   ```sql
   CREATE ROLE iot_platform_app WITH LOGIN REPLICATION PASSWORD '<from Secrets Manager>';
   CREATE DATABASE iot_platform OWNER iot_platform_app;

   CREATE TABLE public.iot_events (
     id          BIGSERIAL PRIMARY KEY,
     device_id   VARCHAR(64)              NOT NULL,
     timestamp   TIMESTAMP WITH TIME ZONE NOT NULL,
     latitude    DOUBLE PRECISION,
     longitude   DOUBLE PRECISION,
     temperature DOUBLE PRECISION,
     humidity    DOUBLE PRECISION,
     heart_rate  DOUBLE PRECISION,
     battery     DOUBLE PRECISION
   );
   ```

5. Store the `iot_platform_app` password in a new secret
   `iot-hackathon/postgres/iot_platform-credentials`.

> The `id BIGSERIAL PRIMARY KEY` is required so Debezium can derive change‑event
> keys for logical replication.

---

## Verification

- `systemctl is-active postgresql` → `active`.
- `SHOW wal_level;` → `logical`.
- The `iot_platform` database, `iot_platform_app` role (with `LOGIN` +
  `REPLICATION`), and `iot_events` table all exist.
- From the **Bastion** Session Manager shell, a TCP connection to
  `<POSTGRES_PRIVATE_IP>:5432` succeeds — proving the security group rule works
  without any change.

---

## Issues encountered & fixes

1. **`curl` vs `curl-minimal` package conflict.** Amazon Linux 2023 ships
   `curl-minimal`; explicitly installing `curl` aborts `dnf` (and, under
   `set -e`, the whole bootstrap). **Fix:** don't install `curl` — the
   pre‑installed `curl-minimal` is sufficient. This same fix recurs on the
   Kafka hosts.
2. **`DO $$…$$` blocks break psql `:'var'` substitution.** Wrapping the role/
   DB creation in a dollar‑quoted block prevented client‑side variable
   substitution. **Fix:** use top‑level `SELECT … WHERE NOT EXISTS (…) \gexec`
   statements (idempotent and substitute correctly).
3. **Security incident — password echoed to a log.** `set -x` tracing was
   active around a `psql -v dbpass=…` call, writing the plaintext password
   into `/var/log/…`. **Fix:** rotated the secret to a fresh 32‑char value,
   put the password only inside the SQL heredoc body (never on a traced
   command line), and redacted the log. See
   [operations/security.md](../operations/security.md).

---

Next: [06 · Kafka Broker](./06-kafka-broker.md)
