# Task: Deploy Apache Kafka Server — EC2 Host Setup

**Date:** 2026-07-11
**Scope:** Deploy ONE EC2 instance to later host Apache Kafka, and install Docker, Docker Compose, and Java 17 on it. **Kafka itself was not deployed** — that is a separate, later task, per instructions.

---

## Stack Name Note

The originally-planned stack name `IotHackathon-Kafka` was still occupied by the old Amazon MSK
stack (mid-creation at the time). Per your explicit choice, this EC2 instance was deployed under
a different name, **`IotHackathon-KafkaBroker`**, rather than waiting. The MSK cluster has since
reached `ACTIVE`/`CREATE_COMPLETE` — its cleanup is a separate, previously-approved task not
executed as part of this one (flagged separately, not auto-started).

---

## Resources Created

| Resource | Detail |
|---|---|
| CloudFormation stack | `IotHackathon-KafkaBroker` — CREATE_COMPLETE |
| IAM Role | `KafkaBrokerInstanceRole` — `AmazonSSMManagedInstanceCore` only (no custom policy; MSK/IAM-auth permissions are no longer needed under the self-managed Kafka design) |
| IAM Instance Profile | Auto-created by CDK, attached to the instance |
| EC2 Instance | `i-0fd77521796b8c71e`, tag `Name=iot-hackathon-kafka-broker` |

### EC2 Specification

| Property | Value |
|---|---|
| Instance ID | `i-0fd77521796b8c71e` |
| Type | t3.large |
| AMI | `ami-0fd6240f599091088` (Amazon Linux 2023) |
| State | running |
| Private IP | `10.42.2.152` |
| Public IP | none (private subnet, no public SSH) |
| Subnet | `subnet-0b48a9b72ff904555` (existing, `IotHackathon-Network`) |
| Security Group | `sg-02b40d867975ba242` (existing `MskSg`, reused as-is) |
| IAM Instance Profile | `IotHackathon-KafkaBroker-KafkaBrokerInstanceInstanceProfileDF99CC14-xDjweWNtvUSr` |
| Root volume | 30 GiB gp3, encrypted |
| Access | SSM Session Manager only — no SSH key, no public SSH |

**On "reuse existing IAM Role":** no existing role in the account matched this instance's
minimal need (SSM-only), so a new role was created using the same `AmazonSSMManagedInstanceCore`
managed-policy pattern already used by the Postgres and Bastion instance roles, rather than
inventing new permissions. Flagging this so you can redirect if you meant literally attaching an
existing role object.

---

## Bug Found and Fixed

The first UserData run **failed silently at the `dnf install` step**: it tried to install the
full `curl` package, which conflicts with `curl-minimal` (pre-installed by default on Amazon
Linux 2023) — the exact same conflict already fixed in the PostgreSQL stack's UserData earlier in
this project, which I missed applying here. Because the script uses `set -e`, the whole install
aborted and Docker/Compose/Java were never installed.

**Fix:** removed `curl` from the package list (the pre-installed `curl-minimal` already provides
everything the script needs) in `infra/kafka/stacks/kafka_broker_stack.py`, and re-ran the
corrected install commands on the already-running instance via SSM Run Command rather than
replacing the instance. The source code is now fixed for any future redeploys too.

---

## Validation Results

All checks run via SSM Run Command (no SSH):

| Check | Result |
|---|---|
| EC2 running | ✅ `state: running` |
| Docker installed and active | ✅ `Docker version 25.0.14, build 0bab007`, `systemctl is-active docker` → `active` |
| Docker Compose working | ✅ `Docker Compose version v2.29.7` |
| Java 17 installed | ✅ `openjdk version "17.0.19"`, Amazon Corretto 17.0.19.10.1 |
| Docker functional test | ✅ `docker run --rm hello-world` completed successfully |

No Kafka, Kafka Connect, PostgreSQL, Debezium, or Snowflake components were installed or
configured, per instructions.

---

## Next Step

Awaiting approval for the next task. Two independent things are ready and unstarted:
1. **Deploy Kafka itself** (Docker Compose, KRaft mode) on this now-ready host.
2. **MSK cleanup** — the old `IotHackathon-Kafka` cluster is now `ACTIVE`, so the previously-approved delete/verify/report sequence can run whenever you want it to.
