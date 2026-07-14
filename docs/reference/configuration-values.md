# Configuration Values Reference

Every placeholder used across this repository and its documentation is listed
here. Before you deploy, gather your own values for each one. **None of these
are secrets** (real secrets live only in AWS Secrets Manager and never appear
in the repo) — they are environment‑specific identifiers you fill in.

Placeholders appear in angle brackets, e.g. `<AWS_ACCOUNT_ID>`, both in the
docs and in the committed source files (CDK stacks, connector configs, SQL).

---

## Account & region

| Placeholder | What it is | Where to find it |
|---|---|---|
| `<AWS_ACCOUNT_ID>` | Your 12‑digit AWS account ID | Console top‑right → account menu, or STS "get caller identity" |
| `us-east-1` | Deployment region (used throughout) | Chosen for this project |
| `<SNOWFLAKE_ACCOUNT>` | Snowflake account identifier, e.g. `ORG-ACCOUNT` | Snowsight → Admin → Accounts, or the login URL |
| `<YOUR_ADMIN_EMAIL>` | Email that receives the IoT Device Simulator Cognito invite | You choose |

## Networking (created by the network foundation stack)

| Placeholder | What it is |
|---|---|
| `<VPC_ID>` | VPC id (`vpc-…`) of the project VPC (CIDR `10.42.0.0/16`) |
| `<PUBLIC_SUBNET_AZ1>` / `<PUBLIC_SUBNET_AZ2>` | Public subnet ids |
| `<PRIVATE_SUBNET_AZ1>` / `<PRIVATE_SUBNET_AZ2>` | Private subnet ids |
| `<POSTGRES_SG_ID>` | Security group for the PostgreSQL instance (allows 5432 from Bastion + Kafka‑client SGs) |
| `<BASTION_SG_ID>` | Bastion security group (no inbound; SSM only) |
| `<KAFKA_BROKER_SG_ID>` | Broker security group (allows 9092 from the Kafka‑client SG) |
| `<KAFKA_CLIENT_SG_ID>` | Client security group used by Kafka Connect + the Lambda bridge (allows 8083 from Bastion) |

## Instances (created as you deploy each stage)

| Placeholder | What it is |
|---|---|
| `<POSTGRES_PRIVATE_IP>` | Private IP of the PostgreSQL EC2 instance |
| `<KAFKA_BROKER_PRIVATE_IP>` | Private IP of the Kafka broker EC2 instance |
| `<KAFKA_BROKER_INSTANCE_ID>` | Instance id of the Kafka broker |
| `<KAFKA_CONNECT_INSTANCE_ID>` | Instance id of the Kafka Connect worker |

## Storage & secrets

| Placeholder | What it is |
|---|---|
| `iot-hackathon-iot-backup-<AWS_ACCOUNT_ID>-us-east-1` | S3 raw‑backup bucket name |
| `<SUFFIX>` | The 6‑character random suffix AWS appends to a Secrets Manager secret ARN |
| `<YOUR_RSA_PUBLIC_KEY_BODY>` | The base64 body of an RSA public key you generate for a Snowflake service user |

## Secrets Manager secret names (values live only in AWS, never in the repo)

| Secret name | Contains |
|---|---|
| `iot-hackathon/postgres/credentials` | Original database credentials (network/security foundation) |
| `iot-hackathon/postgres/iot_platform-credentials` | `iot_platform_app` role password |
| `iot-hackathon/snowflake/kafka-connector-key` | Snowflake Kafka connector private key + connection metadata |
| `iot-hackathon/snowflake/dbt-key` | dbt private key + connection metadata |
| `iot-hackathon/snowflake/streamlit-key` | Streamlit private key + connection metadata |

---

## Generating an RSA key pair for a Snowflake user

Each Snowflake service user needs its own key pair. Generate one locally (or on
a trusted host), store the **private** key in Secrets Manager, and paste the
**public** key body into the relevant `infra/snowflake/*.sql` script:

```bash
# private key (PKCS#8, unencrypted)
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -outform PEM -nocrypt -out rsa_key.p8
# public key
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
# the single-line body to paste as <YOUR_RSA_PUBLIC_KEY_BODY>
grep -v 'KEY-----' rsa_key.pub | tr -d '\n'
```

Store the private key as a Secrets Manager secret; never commit it.
