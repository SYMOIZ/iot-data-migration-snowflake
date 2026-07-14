# AWS Hackathon — Global Instructions

## Approved Architecture (do not change)

```
AWS IoT Device Simulator → AWS IoT Core → Self-managed Apache Kafka (KRaft, Docker Compose on EC2)
→ Kafka Connect on EC2 → PostgreSQL on EC2 → Debezium CDC → Kafka (CDC topic) → Snowflake → dbt → Streamlit
```

**2026-07-11 revision:** Amazon MSK was replaced with a self-managed Apache Kafka broker
(KRaft mode, no ZooKeeper) running via Docker Compose on a dedicated EC2 instance. This was an
explicit, approved architecture change (not an implementation detail) — the `IotHackathon-Kafka`
CloudFormation stack that provisioned the MSK cluster is being decommissioned. Kafka Connect
still runs separately on its own EC2 instance via Docker Compose, as previously decided.

## Deployment workflow

- Work proceeds in explicitly user-approved steps. Never start the next step until the user
  explicitly approves it, even if a prior message described what that step involves.
- Before any destructive AWS action (delete/terminate/release), list candidates and get
  explicit approval — never force-delete without confirmation.
- Never touch `IotHackathon-Network` or `IotHackathon-Security` (or any other stack the user
  has designated as a reused foundation) unless explicitly told to.

## AWS IoT Device Simulator — Admin Email

If deploying the AWS IoT Device Simulator through CloudFormation and the template requires an
`Admin Email` parameter, **stop and ask the user for the email address** instead of using a
placeholder, guessing, or reusing an unrelated email found elsewhere in the session. Wait for
the user to provide the email, then continue the deployment with it.
