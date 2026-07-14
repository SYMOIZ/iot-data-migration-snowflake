# 00 · Prerequisites

Complete these before starting the deployment steps.

---

## Accounts

- **AWS account** with permissions to create VPC/EC2/IAM/Lambda/IoT/S3/
  Secrets Manager/CloudFormation resources. All steps use region **`us-east-1`**.
- **Snowflake account** with `ACCOUNTADMIN` access (needed to create
  warehouses, databases, roles, and users).

## Tools (only needed for the IaC / CLI portions)

Most stages can be driven from the **AWS Management Console**. The
infrastructure was originally built with AWS CDK, and a few stages (installing
software on EC2, registering Kafka connectors, running dbt) are inherently
command‑line. For those you'll want:

| Tool | Used for |
|---|---|
| AWS CLI v2 | Optional; console equivalents are documented throughout |
| AWS CDK v2 (`npm i -g aws-cdk`) + Python 3.11+ | Deploying the `infra/**` stacks as code (optional alternative to console) |
| A browser | Console + Snowsight + the Device Simulator UI + the dashboard |

> The infrastructure code under `infra/` is provided as a **reproducible
> reference**. You can deploy each stage either by following the console steps
> in these docs, or by running the matching CDK stack. Both are documented.

## Naming conventions used throughout

- CloudFormation stacks are prefixed `IotHackathon-…`
- Resources are tagged `project=iot-hackathon`
- Region is `us-east-1`

## Gather your configuration values

Open [reference/configuration-values.md](../reference/configuration-values.md)
and keep it beside you. As you create resources you'll fill in the VPC id,
subnet ids, security group ids, instance IPs, your AWS account id, and your
Snowflake account identifier.

## Core principles (applied at every step)

1. **No SSH.** Every EC2 instance is administered through **SSM Session
   Manager**. Instances have IAM role `AmazonSSMManagedInstanceCore` and no
   key pair.
2. **No public IPs** except the Streamlit dashboard host.
3. **No static passwords.** Credentials come from Secrets Manager; Snowflake
   uses RSA key pairs.
4. **Least privilege.** Each service has its own scoped IAM/Snowflake role.
5. **Never commit secrets.** Only public keys and Secrets Manager *references*
   appear in the repo.

## Cost awareness

The always‑on cost drivers are the NAT Gateway, the VPC interface endpoints,
four `t3.large`/`t3.micro`/`t3.small` EC2 instances, the Snowflake warehouse
(auto‑suspends after 60s), and the S3 bucket. Suspend or terminate resources
when not in use. See [operations/troubleshooting.md](../operations/troubleshooting.md)
for teardown notes.

---

Next: [01 · Network Foundation](./01-network-foundation.md)
