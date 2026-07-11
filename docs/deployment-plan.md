# Deployment Plan — AWS IoT Data Engineering Hackathon

Account: `159412676011` · Region: `us-east-1` · IAM identity: `claude` (AdministratorAccess)

All resources are defined as code (CDK Python under `cdk/`, scripts under `scripts/`) and are
idempotent — `cdk deploy` and the helper scripts can be re-run safely.

## Phase 1 — IoT Ingestion Pipeline

**Flow:** IoT Simulator → AWS IoT Core (MQTT/SigV4) → Lambda → MSK topic `iot-events` →
MSK Connect (Debezium JDBC Sink) → PostgreSQL on EC2, with S3 as a backup target.

### Resources (all automatic — CDK)

| Stack | Resources |
|---|---|
| `IotHackathon-Network` | VPC (10.42.0.0/16, 2 AZs), 2 public + 2 private subnets, 1 NAT Gateway, IGW, route tables, S3 gateway endpoint, 4 interface endpoints (SSM/SSMMessages/EC2Messages/SecretsManager), 4 security groups |
| `IotHackathon-Security` | Secrets Manager secret (Postgres creds, auto-generated password), S3 backup bucket (versioned, encrypted), S3 Connect-plugins bucket + upload of Debezium JDBC-sink and Postgres-source plugin ZIPs |
| `IotHackathon-Database` | PostgreSQL 15 EC2 (t3.micro, private subnet, gp3 20GB, WAL logical, `iot` DB, `iot_events` table, publication `dbz_publication`), Bastion EC2 (t3.micro, public subnet, SSM-only, no SSH key, no inbound rules) |
| `IotHackathon-Msk` | MSK provisioned cluster (2× kafka.t3.small, IAM auth, TLS in-transit, CloudWatch broker logs), MSK Connect (2 custom plugins, 1 worker config, 1 JDBC-sink connector: `iot-events` → `iot_events` table), CloudWatch CPU alarm |
| `IotHackathon-Iot` | 5 IoT Things, Lambda (`kafka-python` layer, IAM-auth producer), IoT Topic Rule (`iot/+/telemetry` → Lambda), CloudWatch error alarm |

### Dependencies
Network → Security → Database → MSK → IoT (each stack declares `add_dependency` on the CDK app; `cdk deploy --all` orders them automatically).

### Estimated cost (us-east-1, running continuously)

| Item | Est. monthly | Notes |
|---|---|---|
| NAT Gateway | ~$32 + ~$0.045/GB | 1 gateway, single AZ |
| MSK brokers (2× kafka.t3.small) | ~$60 | $0.0416/hr × 2 |
| MSK broker EBS (2×20GB gp3-equivalent) | ~$4 | |
| MSK Connect (1 connector, 1 MCU × 1 worker) | ~$80 | $0.1106/MCU-hr |
| EC2 Postgres (t3.micro) + Bastion (t3.micro) | ~$15 | on-demand, 2× t3.micro |
| EBS (Postgres 20GB gp3) | ~$1.6 | |
| VPC interface endpoints (4×, 2 AZs) | ~$58 | $0.01/hr each — see note below |
| Secrets Manager | ~$0.40 | 1 secret |
| S3 (backup + plugins) | <$1 | low volume |
| CloudWatch Logs/Alarms | ~$1–3 | |
| **Total** | **~$250–260/month** (~$8.50/day) | Interface endpoints are the biggest lever — see below |

**Cost lever:** the 4 VPC interface endpoints (SSM/SSMMessages/EC2Messages/SecretsManager) cost about
as much as the NAT Gateway they're meant to reduce reliance on. If you want to cut cost, I can drop
them and rely solely on the NAT Gateway for that traffic (private EC2 still has full outbound via
NAT) — saves ~$58/month at a small security-posture cost (SSM/Secrets Manager traffic would traverse
the NAT/IGW path instead of staying on the AWS private network). Default as built: both are present
(defense-in-depth); tell me if you'd rather trim it.

**Not included above:** data transfer, and IoT Core message costs (negligible at 5 simulated devices).
Destroying the stacks (`cdk destroy --all`) stops all of the above except the S3 backup bucket, which
is retained by design (`RemovalPolicy.RETAIN`) so simulation data isn't lost accidentally.

### Deployment time
- `cdk bootstrap`: done (~1 min, already complete).
- `cdk deploy --all`: **~25–35 minutes** (MSK cluster creation alone is typically 20-25 min).

### Manual steps
None required for Phase 1 — everything above is CDK/CLI automated.

---

## Phase 2 — CDC, Snowflake, dbt, Streamlit, Timestream/Grafana

**Flow:** Postgres WAL → Debezium (MSK Connect) → MSK topic `cdc.public.iot_events` → Snowflake
Kafka Connector → Snowflake `RAW` (Bronze) → dbt → `CLEAN` (Silver) → `ANALYTICS` (Gold) → Streamlit;
parallel path → Lambda → Timestream → Grafana.

### Resources & automation split

| Component | Automatable here? | How |
|---|---|---|
| Debezium Postgres source connector | **Yes** | `scripts/deploy-debezium-connector.sh` creates the MSK Connect connector via AWS CLI once you confirm Phase 1 data is flowing (plugin already uploaded in Phase 1) |
| dbt project (bronze/silver/gold models + docs) | **Yes** | Generated now under `dbt/`, runs once Snowflake credentials exist |
| Streamlit dashboard | **Yes** | Generated now under `streamlit/`, points at Snowflake Gold |
| Timestream + Lambda writer | **Yes** | CDK stack + Lambda reading Snowflake, writing Timestream |
| Grafana | **Partially** | Self-hosted via Docker Compose (`grafana/docker-compose.yml`) can be automated; Amazon Managed Grafana requires IAM Identity Center setup, which typically needs a one-time manual step (see `NEXT_MANUAL_STEPS.md`) |
| **Snowflake account + Kafka Connector config** | **No — manual** | Snowflake account creation and the connector's key-pair auth secret must be created by you (see below) |

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
| Debezium source connector (1 MCU × 1 worker) | ~$80 |
| Timestream (writes + storage, low volume) | ~$5–15 |
| Lambda (Timestream writer, low volume) | <$1 |
| Grafana (self-hosted on existing infra) | $0 extra, or Amazon Managed Grafana ~$9/user/month |
| Snowflake | Free trial credits, then usage-based (outside AWS billing) |

### Deployment time
~15–20 minutes once Snowflake credentials are provided (connector deploy + dbt run + Streamlit start).

---

## Recommendation

Given the ~$250-260/month run rate if left on continuously, I'd suggest treating this as a
**deploy → demo/test → `cdk destroy` when not in use** workflow rather than leaving it running,
unless you want it up persistently. `cdk deploy --all` and `cdk destroy --all` are both idempotent
and safe to repeat.

**I will not run `cdk deploy` until you confirm you want to proceed** — this is the point where
real billing starts. Everything up to here (code, plugin packaging, bootstrap) is free or effectively
free (~$0.02/month for the CDK bootstrap S3 bucket).
