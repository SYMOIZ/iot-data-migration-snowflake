# STEP 2 Report — Database Infrastructure (PostgreSQL + Bastion)

**Date:** 2026-07-11
**Status:** ✅ **STEP 2 COMPLETE** — awaiting approval before Step 3
**Scope:** PostgreSQL EC2 (on-prem simulation), Bastion Host, IAM instance profiles, EBS volume, WAL/Debezium prep, database/user/permissions. Reused the existing `IotHackathon-Network` and `IotHackathon-Security` stacks — created no VPC, subnet, IAM (beyond the two new instance roles required for this step), Secrets Manager, or S3 resources.

**Out of scope, not touched:** Amazon MSK, Kafka Connect, Debezium connector deployment, Snowflake, dbt, Streamlit.

---

## 1. Approach

Deployed as a new AWS CDK (Python) stack, `IotHackathon-Database`, at `infra/database/` in this repo — matching the SRS's mandated IaC tool and the CDK-managed pattern of the existing stacks. The stack **imports** the existing VPC, private subnets, `PostgresSg`, `BastionSg`, and the `iot-hackathon/postgres/credentials` secret by ID/ARN (all as read-only/`mutable=False` references) and creates only new resources. `cdk diff` was reviewed before every deploy to confirm no changes ever touched `IotHackathon-Network` or `IotHackathon-Security`.

## 2. Resources Created

| Resource | Detail |
|---|---|
| CloudFormation stack | `IotHackathon-Database` — `UPDATE_COMPLETE` |
| PostgreSQL EC2 | `i-08633055f8bc44815`, `t3.large`, private subnet `subnet-0b48a9b72ff904555` (us-east-1a), private IP `10.42.2.174`, no public IP |
| Bastion EC2 | `i-0b936de07aea155fb`, `t3.micro`, same private subnet, private IP `10.42.2.161`, no public IP |
| IAM Role + Instance Profile | `PostgresInstanceRole` — `AmazonSSMManagedInstanceCore` + scoped `secretsmanager:GetSecretValue`/`DescribeSecret` on the one DB credentials secret ARN only |
| IAM Role + Instance Profile | `BastionInstanceRole` — `AmazonSSMManagedInstanceCore` only (no Secrets Manager access; least privilege) |
| EBS data volume | 30 GiB `gp3`, encrypted, attached to the Postgres instance at `/dev/sdf`, mounted at `/var/lib/pgsql` (PGDATA lives on the dedicated volume, not the root disk) |
| Security groups | **None created.** Reused existing `PostgresSg` (already allowed 5432 from `BastionSg` + `MskClientSg`) and `BastionSg` (SSM-only, no inbound needed) — verified sufficient, see §4 |

Both instances use Amazon Linux 2023, SSM Session Manager only (no SSH key, no public IP, no inbound port 22 anywhere), and `require_imdsv2=True`.

## 3. PostgreSQL Configuration

- `wal_level = logical`, `max_wal_senders = 10`, `max_replication_slots = 10` — ready for Debezium logical replication in a later step
- `listen_addresses = '*'`, `pg_hba.conf` allows `host`/`host replication` from `10.42.0.0/16` (VPC CIDR only) via `scram-sha-256`
- Database `iot` and role `iot_admin` (LOGIN, REPLICATION) created, credentials sourced from the existing `iot-hackathon/postgres/credentials` Secrets Manager secret — the instance fetches this at boot using its IAM role; the password is never hardcoded in code, CloudFormation, or this report
- Bootstrap script is idempotent (safe to re-run: skips already-formatted volumes, already-initialized data directories, already-created roles/databases)

## 4. Security Group Investigation (no changes made)

Before writing any code, the existing rules were checked directly:
- `PostgresSg` already allows TCP 5432 from `BastionSg` ("Bastion admin access to Postgres") and from `MskClientSg` ("Kafka Connect JDBC sink access") — both pre-provisioned by `IotHackathon-Network` for exactly this purpose.
- `BastionSg` has no inbound rules at all (by design — SSM Session Manager is outbound-initiated from the instance, no inbound needed).
- All four VPC interface-endpoint security groups (EC2 Messages, SSM, SSM Messages, Secrets Manager) already allow 443 from the full VPC CIDR.

**Conclusion: zero security group changes were required.** This was verified functionally, not just by rule inspection — see §5.

## 5. Verification Performed

| Check | Result |
|---|---|
| `IotHackathon-Database` stack status | `UPDATE_COMPLETE` |
| Both instances | `running`, registered `Online` in SSM |
| `systemctl is-active postgresql` | `active` |
| `SHOW wal_level;` | `logical` |
| Database `iot` exists | confirmed |
| Role `iot_admin` (`rolreplication`, `rolcanlogin`) | both `true` |
| Auth test: `iot_admin` → `iot` over TCP (host, not local socket) | **succeeded** — exercises the actual `pg_hba.conf` rule, password fetched from Secrets Manager and never displayed |
| Network test: Bastion → Postgres `10.42.2.174:5432` | **TCP reachable** — confirms `PostgresSg` rule works end-to-end without modification |
| `IotHackathon-Network` / `IotHackathon-Security` / `CDKToolkit` | `LastUpdatedTime` unchanged from Step 1 — confirmed untouched |
| Dedicated data volume | mounted at `/var/lib/pgsql`, 30 GiB, ~1% used |

## 6. Problems Found & Resolved

Two bugs were hit and fixed during deployment — documented in full for transparency:

1. **Package conflict:** the first UserData attempt explicitly installed `curl`, which conflicts with Amazon Linux 2023's default `curl-minimal` package. The `dnf install` transaction failed, and under `set -e` the entire bootstrap script aborted before PostgreSQL was even installed. **Fix:** removed the explicit `curl` dependency (AL2023's built-in `curl-minimal` already provides everything the script needs); the CDK source (`infra/database/stacks/database_stack.py`) was corrected and the corrected script verified via a full re-run.

2. **SQL syntax error:** an early idempotency rewrite wrapped the `CREATE ROLE`/`CREATE DATABASE` logic in a `DO $$ ... $$` block, but psql's `:'var'` client-side substitution does not apply inside dollar-quoted bodies, causing a syntax error and leaving the role/database uncreated. **Fix:** switched to plain top-level `SELECT ... WHERE NOT EXISTS (...) \gexec` statements, which are idempotent and substitute correctly. Verified by re-running and confirming the role/database now exist.

**Security incident — credential exposure, self-detected and remediated:** during the failed run described in bug #1 → #2 sequence, an intermediate attempt ran with `set -x` still active around the Secrets Manager retrieval, causing the database password to be written in plaintext to `/var/log/user-data.log` on the Postgres instance (and consequently visible in the SSM command output used to diagnose the failure). Because the `CREATE ROLE` statement never actually succeeded at that point (it failed on the SQL syntax error immediately after), the leaked password was never applied to any live credential — but it was treated as compromised regardless. **Remediation taken immediately, before any further deployment:**
- Rotated the `iot-hackathon/postgres/credentials` secret's password to a freshly generated 32-character value via `aws secretsmanager put-secret-value`, without the new value ever being printed or logged
- Fixed the script to wrap the Secrets Manager retrieval and `psql` invocation in `set +x` / `set -x`, so command tracing never echoes secret values again (confirmed via `grep -ci password /var/log/user-data.log` → `0` after the corrected run)
- The final, verified deployment created the database role using only the rotated password, fetched fresh from Secrets Manager on the instance itself

No other credentials in this account were affected. The rotated secret is what the deployed `iot_admin` role's password currently matches.

## 7. Remaining Resources — Full Picture After Step 2

| Stack | Status |
|---|---|
| `IotHackathon-Network` | `CREATE_COMPLETE` (Step 1, unchanged) |
| `IotHackathon-Security` | `CREATE_COMPLETE` (Step 1, unchanged) |
| `CDKToolkit` | `CREATE_COMPLETE` (unchanged) |
| `IotHackathon-Database` | `UPDATE_COMPLETE` (new, this step) |

No MSK, no Kafka Connect, no Debezium, no Snowflake, no dbt, no Streamlit were deployed — confirmed out of scope for this step and not created.

## 8. Recommendations for Later Steps (not acted on)

- Root EBS volumes (8 GiB each, both instances) are unencrypted — only the dedicated 30 GiB Postgres data volume was explicitly encrypted. Consider enabling account-level "EBS encryption by default" for us-east-1 before further instances are launched.
- The `iot` schema currently has no application tables — table creation was intentionally left out of this step's scope (it belongs with the Kafka Connect JDBC Sink Connector work in the next phase, per the hackathon brief).

## 9. Next Step

Step 2 (Database Infrastructure) is complete and verified end-to-end. Per the approved architecture, Step 3 would be Amazon MSK + Kafka Connect + Debezium CDC — **not started**.

**Awaiting your approval before starting Step 3.**
