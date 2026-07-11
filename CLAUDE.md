# AWS Hackathon — Global Instructions

## Approved Architecture (do not change)

```
AWS IoT Device Simulator → AWS IoT Core → Amazon MSK → Kafka Connect on EC2
→ PostgreSQL on EC2 → Debezium CDC → Kafka MSK (CDC topic) → Snowflake → dbt → Streamlit
```

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
