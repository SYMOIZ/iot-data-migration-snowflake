# Deployment Plan — AWS IoT Data Engineering Hackathon

Account: `159412676011` · Region: `us-east-1` · IAM identity: `claude` (AdministratorAccess)

All resources are defined as code (CDK Python under `cdk/`, scripts under `scripts/`) and are
idempotent — `cdk deploy` and the helper scripts can be re-run safely.

## Phase 1 — IoT Ingestion Pipeline

**Flow:** IoT Simulator → AWS IoT Core (MQTT/SigV4) → Lambda → MSK topic `iot-events` →
self-managed Kafka Connect (EC2, Docker Compose, Debezium JDBC Sink connector) →
PostgreSQL on EC2, with S3 available as a backup target.

**Architecture note:** Kafka Connect runs on a dedicated EC2 host (Docker Compose), not Amazon
MSK Connect — MSK provides the Kafka cluster only. The worker authenticates to MSK with IAM
(`aws-msk-iam-auth`), runs Debezium's Kafka Connect distribution, and is pre-loaded with the
Debezium JDBC Sink connector (`iot-events` → `iot_events` table), the built-in Debezium Postgres
source connector (used in Phase 2), and the Snowflake Kafka Connector jar staged for Phase 2.

### Resources (all automatic — CDK, deployed stack by stack)

| Stack | Resources |
|---|---|
| `IotHackathon-Network` | VPC (10.42.0.0/16, 2 AZs), 2 public + 2 private subnets, 1 NAT Gateway, IGW, route tables, S3 gateway endpoint, 4 interface endpoints (SSM/SSMMessages/EC2Messages/SecretsManager), 4 security groups |
| `IotHackathon-Security` | Secrets Manager secret (Postgres creds, auto-generated password), S3 backup bucket (versioned, encrypted) |
| `IotHackathon-Database` | PostgreSQL 15 EC2 (t3.micro, private subnet, gp3 20GB, WAL logical, `iot` DB, `iot_events` table, publication `dbz_publication`), Bastion EC2 (t3.micro, public subnet, SSM-only, no SSH key, no inbound rules) |
| `IotHackathon-Msk` | MSK provisioned cluster (2× kafka.t3.small, IAM auth, TLS in-transit, CloudWatch broker logs), CloudWatch CPU alarm |
| `IotHackathon-KafkaConnect` | EC2 (t3.large, private subnet, gp3 30GB), Docker Compose running Debezium Connect + JDBC-sink/Postgres-source/Snowflake connector plugins, IAM role scoped to the MSK cluster/topic |
| `IotHackathon-Iot` | 5 IoT Things, Lambda (`kafka-python` layer, IAM-auth producer), IoT Topic Rule (`iot/+/telemetry` → Lambda), CloudWatch error alarm |

### Dependencies & deploy order
Network → Security → Database → Msk → KafkaConnect → Iot. Deploying **stack by stack** (not
`cdk deploy --all`) so each can be verified before the next starts:
```
cdk deploy IotHackathon-Network
cdk deploy IotHackathon-Security
cdk deploy IotHackathon-Database
cdk deploy IotHackathon-Msk
cdk deploy IotHackathon-KafkaConnect
cdk deploy IotHackathon-Iot
```

### Estimated cost (us-east-1, running continuously)

| Item | Est. monthly | Notes |
|---|---|---|
| NAT Gateway | ~$32 + ~$0.045/GB | 1 gateway, single AZ |
| MSK brokers (2× kafka.t3.small) | ~$60 | $0.0416/hr × 2 |
| MSK broker EBS (2×20GB) | ~$4 | |
| Kafka Connect EC2 (t3.large) | ~$60 | on-demand |
| Kafka Connect EBS (30GB gp3) | ~$2.4 | |
| EC2 Postgres (t3.micro) + Bastion (t3.micro) | ~$15 | on-demand, 2× t3.micro |
| EBS (Postgres 20GB gp3) | ~$1.6 | |
| VPC interface endpoints (4×, 2 AZs) | ~$58 | $0.01/hr each — see note below |
| Secrets Manager | ~$0.40 | 1 secret |
| S3 (backup) | <$1 | low volume |
| CloudWatch Logs/Alarms | ~$1–3 | |
| **Total** | **~$235–240/month** (~$8/day) | Cheaper than the MSK-Connect design (~$20/month less) |

**Cost lever:** the 4 VPC interface endpoints (SSM/SSMMessages/EC2Messages/SecretsManager) cost about
as much as the NAT Gateway they're meant to reduce reliance on. Left as-is (defense-in-depth); say
the word if you'd rather drop them and save ~$58/month.

**Not included above:** data transfer, and IoT Core message costs (negligible at 5 simulated devices).
Destroying the stacks (`cdk destroy <StackName>`, reverse order) stops all of the above except the
S3 backup bucket, which is retained by design (`RemovalPolicy.RETAIN`).

### Deployment time
- `cdk bootstrap`: done (~1 min, already complete).
- Stack-by-stack `cdk deploy`: **~30–40 minutes total** (MSK cluster creation is the long pole at
  ~20-25 min; Kafka Connect EC2 boot + Docker pulls + plugin downloads adds ~5 min).

### Manual steps
None required for Phase 1 — everything above is CDK/CLI automated.

---

## Phase 2 — CDC, Snowflake, dbt, Streamlit, Timestream/Grafana

**Flow:** Postgres WAL → Debezium (Kafka Connect EC2) → MSK topic `cdc.public.iot_events` →
Snowflake Kafka Connector → Snowflake `RAW` (Bronze) → dbt → `CLEAN` (Silver) → `ANALYTICS` (Gold)
→ Streamlit; parallel path → Lambda → Timestream → Grafana.

### Resources & automation split

| Component | Automatable here? | How |
|---|---|---|
| Debezium Postgres source connector | **Yes** | `scripts/deploy-debezium-connector.sh` PUTs the connector config to the Kafka Connect REST API once you confirm Phase 1 data is flowing (plugin already staged on the EC2 host) |
| Snowflake Kafka Connector instance | **Yes, once creds exist** | `scripts/deploy-snowflake-connector.sh` (jar already staged on the EC2 host) |
| dbt project (bronze/silver/gold models + docs) | **Yes** | Generated now under `dbt/`, runs once Snowflake credentials exist |
| Streamlit dashboard | **Yes** | Generated now under `streamlit/`, points at Snowflake Gold |
| Timestream + Lambda writer | **Yes** | CDK stack + Lambda reading Snowflake, writing Timestream |
| Grafana | **Partially** | Self-hosted via Docker Compose (`grafana/docker-compose.yml`) can be automated; Amazon Managed Grafana requires IAM Identity Center setup, which typically needs a one-time manual step (see `NEXT_MANUAL_STEPS.md`) |
| **Snowflake account + key pair registration** | **No — manual** | Snowflake account creation and registering the public key must be done by you (see below) |

### Manual step required (Snowflake)
I cannot create a Snowflake account or generate its key pair on your behalf — that needs your
Snowflake login. Once you have:
1. A Snowflake account (free trial is fine) and its account identifier (e.g. `xy12345.us-east-1`)
2. A key pair generated for Snowflake key-pair auth (I can generate this key pair for you locally
   and give you the public key to register in Snowflake — I just can't create the Snowflake user)
3. Database `HACKATHON_IOT` with schemas `RAW`, `CLEAN`, `ANALYTICS`

...tell me and I will store the private key in Secrets Manager, configure the Snowflake Kafka
Connector, and finish the rest of Phase 2 automatically.

### Estimated cost (Phase 2 additions)
| Item | Est. monthly |
|---|---|
| Debezium source connector | $0 extra (runs on the existing Kafka Connect EC2) |
| Timestream (writes + storage, low volume) | ~$5–15 |
| Lambda (Timestream writer, low volume) | <$1 |
| Grafana (self-hosted on existing infra) | $0 extra, or Amazon Managed Grafana ~$9/user/month |
| Snowflake | Free trial credits, then usage-based (outside AWS billing) |

### Deployment time
~15–20 minutes once Snowflake credentials are provided (connector deploy + dbt run + Streamlit start).

---

## Recommendation

Given the ~$235-240/month run rate if left on continuously, I'd suggest treating this as a
**deploy → demo/test → `cdk destroy` when not in use** workflow rather than leaving it running,
unless you want it up persistently. Every `cdk deploy` / `cdk destroy` is idempotent and safe to
repeat.

Proceeding now to deploy Phase 1 stack by stack per your instruction.
