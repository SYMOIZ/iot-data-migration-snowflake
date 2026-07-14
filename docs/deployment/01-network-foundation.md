# 01 · Network Foundation

**Stack:** `IotHackathon-Network` · **Purpose:** the VPC, subnets, routing,
security groups, and VPC endpoints that every later stage runs inside.

This is the base layer. Compute lives in private subnets with no public IPs;
administration is via SSM, which is why the VPC endpoints below are required.

> IaC reference: this foundation is imported (never modified) by every later
> CDK stack. If you prefer code, create the equivalent of the values in
> [reference/configuration-values.md](../reference/configuration-values.md).

---

## What to create

| Resource | Value |
|---|---|
| VPC | CIDR `10.42.0.0/16`, tag `Name=iot-hackathon-vpc` |
| Public subnets | 2, one per AZ (`us-east-1a`, `us-east-1b`) |
| Private subnets | 2, one per AZ |
| Internet Gateway | attached to the VPC |
| NAT Gateway | 1, in a public subnet, with an Elastic IP |
| Route tables | public → IGW; private → NAT |
| VPC endpoints | `ssm`, `ssmmessages`, `ec2messages`, `secretsmanager` (Interface), `s3` (Gateway) |
| Security groups | Postgres, Bastion, Kafka‑broker, Kafka‑client (see below) |

### Security groups

| SG | Inbound rules | Notes |
|---|---|---|
| Postgres (`<POSTGRES_SG_ID>`) | TCP 5432 from Bastion SG and Kafka‑client SG | database access |
| Bastion (`<BASTION_SG_ID>`) | none | SSM is outbound‑initiated |
| Kafka broker (`<KAFKA_BROKER_SG_ID>`) | TCP 9092 from Kafka‑client SG | broker listener |
| Kafka client (`<KAFKA_CLIENT_SG_ID>`) | TCP 8083 from Bastion SG | Kafka Connect REST API |

---

## Console steps

1. **VPC → Create VPC → "VPC and more".** Set CIDR `10.42.0.0/16`, 2 AZs,
   2 public + 2 private subnets, **1 NAT gateway**, and **enable the S3
   Gateway endpoint**. This wizard creates the VPC, subnets, IGW, NAT, and
   route tables in one shot. Name it `iot-hackathon`.
2. **VPC → Endpoints → Create endpoint** (×4 Interface endpoints):
   `com.amazonaws.us-east-1.ssm`, `.ssmmessages`, `.ec2messages`,
   `.secretsmanager`. Attach them to the **private subnets** and to a security
   group that allows inbound **443 from `10.42.0.0/16`**. These let private
   instances reach SSM and Secrets Manager without internet.
3. **EC2 → Security Groups → Create security group** — create the four groups
   in the table above. Add the inbound rules exactly as listed (reference
   other SGs as the source, not CIDRs).
4. Record the VPC id, all four subnet ids, and all four security‑group ids into
   your configuration‑values sheet.

---

## Verification

- **VPC → Endpoints**: all five show **Status = Available**.
- **Route tables**: the private route table has a `0.0.0.0/0 → NAT` route; the
  public one has `0.0.0.0/0 → IGW`.
- Later stages confirm this works end‑to‑end when their instances register as
  **Online** in **Systems Manager → Fleet Manager** (only possible if the SSM
  endpoints are correct).

## Why each piece exists

- **Interface VPC endpoints (SSM/EC2 messages/Secrets Manager)** are what make
  "no SSH, no public IP" possible — private instances reach these AWS services
  privately.
- **NAT Gateway** lets private instances pull OS packages, Docker images, and
  connector plugins outbound while staying unreachable from the internet.

---

Next: [02 · Security Foundation](./02-security-foundation.md)
