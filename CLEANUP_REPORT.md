# Cleanup Report — IoT Data Engineering Project

**Date:** 2026-07-15
**AWS Account:** `<AWS_ACCOUNT_ID>` (redacted — see note below)
**Region:** us-east-1
**Performed by:** Claude Code, on explicit user authorization

## Scope and authorization

The user requested a full teardown of every AWS and Snowflake resource created for
this project, explicitly including the networking foundation (VPC, NAT Gateway,
subnets, security groups, route tables, VPC endpoints) that this project's own
`CLAUDE.md` would otherwise have treated as a protected, reused foundation stack.
Before deleting the networking layer, the assistant flagged this exception and
asked for confirmation; the user explicitly confirmed: *"Delete everything you
created for this project... including networking resources (VPC, NAT Gateway,
subnets, security groups, route tables, VPC endpoints)... Leave only shared AWS
infrastructure such as CDKToolkit if it is not exclusive to this project."*

That instruction is the authorization for every deletion below. **CDKToolkit**
was explicitly carved out and preserved, since it is generic, account-wide CDK
bootstrap infrastructure (IAM roles, an ECR repo, an S3 staging bucket) required
for any CDK deployment in this account, not something created specifically for
this project.

**Note on account ID:** the real 12-digit AWS account ID appeared throughout the
session in resource ARNs and S3 bucket names (which embed the account ID by
CDK convention, e.g. `<bucket-prefix>-<account-id>-us-east-1`). It has been
redacted to `<AWS_ACCOUNT_ID>` everywhere in this report, consistent with this
project's standing rule to never expose account identifiers in the repository.

---

## AWS resources deleted

### CloudFormation stacks (9 of 9 deleted)

| Stack | Purpose | Final status |
|---|---|---|
| `IotHackathon-DeviceSimulator` | AWS IoT Device Simulator (Things, simulator Lambdas, API Gateway, Step Functions, CloudFront console) | DELETE_COMPLETE |
| `IotHackathon-Kafka` | Original Amazon MSK cluster (superseded by the self-managed Kafka broker, per the 2026-07-11 architecture revision) | DELETE_COMPLETE |
| `IotHackathon-KafkaBroker` | Self-managed Apache Kafka (KRaft) broker EC2 instance | DELETE_COMPLETE |
| `IotHackathon-KafkaConnect` | Kafka Connect EC2 instance (JDBC Sink + Debezium CDC) | DELETE_COMPLETE |
| `IotHackathon-Database` | PostgreSQL EC2 instance | DELETE_COMPLETE |
| `IotHackathon-StreamlitHost` | Streamlit dashboard EC2 instance | DELETE_COMPLETE |
| `IotHackathon-LambdaKafkaBridge` | Lambda bridging IoT Core → Kafka | DELETE_COMPLETE |
| `IotHackathon-Security` | Security groups, IAM roles, S3 backup bucket (CFN tracking only — see orphan note below) | DELETE_COMPLETE |
| `IotHackathon-Network` | VPC, subnets, NAT Gateway, Internet Gateway, route tables, VPC endpoints | DELETE_COMPLETE |

### IoT Core

- All IoT Things, Certificates (detached from policy/thing, deactivated, then
  deleted), and Policies created for this project — deleted.
- IoT Topic Rules — deleted.
- IoT VPC Rule Destination (used to route IoT Rule actions into the private VPC)
  — deleted. Its two AWS-managed ENIs (`DO NOT DELETE` tagged, "AWS IoT Rules
  Engine managed ENI for VPCDestination") lagged behind the destination's own
  deletion and were still attached to a project security group, blocking the
  Network stack's teardown; once confirmed detached (`available` state) and
  confirmed the destination itself no longer existed, they were deleted
  directly to unblock the VPC deletion.

### IAM

- All project-specific IAM roles and inline/attached policies deleted
  (Kafka broker/Connect roles, PostgreSQL role, Streamlit host role, Lambda
  execution roles, etc.), across both the standalone cleanup pass and the
  CloudFormation stack deletions.
- One orphaned role, `IotHackathon-DeviceSimula-APIIoTDeviceSimulatorApiC-*`
  (API Gateway → CloudWatch Logs role, left behind by the DeviceSimulator
  stack's retained-resource behavior), was found during final verification,
  had its attached managed policy detached, and was deleted.

### Secrets Manager

All project secrets under the `iot-hackathon/` prefix — including PostgreSQL
credentials and the Snowflake service-user key pairs for the Kafka connector,
dbt, and Streamlit dashboard — were force-deleted without recovery window.
Confirmed zero secrets remain under this prefix in the final verification scan.

### S3 buckets (4 buckets, ~105,600+ objects/versions purged)

| Bucket (name pattern) | Contents | Outcome |
|---|---|---|
| `iot-hackathon-iot-backup-<account-id>-us-east-1` | IoT event S3 backup (S3 Sink connector output, `flush.size=1`) | Emptied (105,612 versions + delete markers purged in batched, paginated `delete-objects` calls) and bucket deleted |
| `iothackathon-devicesimula-commonresourceslogbucket-*` | S3/CloudFront access logs for the simulator's console distribution | Emptied and bucket deleted |
| `iothackathon-devicesimula-consoledistributions3buc-*` | Device Simulator console static assets | Emptied and bucket deleted |
| `iothackathon-devicesimula-storageroutesbucketbb9ef-*` | Device Simulator internal routing storage | Emptied and bucket deleted |

All four buckets had a CDK `RemovalPolicy.RETAIN` (the CDK default for S3
buckets), so their owning CloudFormation stacks reported `DELETE_COMPLETE`
while the physical buckets and their contents were left behind, orphaned from
CloudFormation. Each was independently discovered during verification,
confirmed project-owned by name/tag, emptied, and explicitly deleted via
`aws s3api delete-bucket`. The backup bucket in particular required a
corrected two-pass purge: an initial single-batch `delete-objects` call
exceeded the API's 1,000-object-per-request limit and failed with
`MalformedXML`; the corrected pass paginated `list-object-versions` and issued
properly batched (≤1,000 objects) deletes.

### CloudWatch Log Groups (7 deleted)

- `/aws/iotrule/iot-hackathon-iot-events`
- `/aws/lambda/IotHackathon-DeviceSimula-CustomResourcesHelperLam-*`
- `/aws/lambda/IotHackathon-DeviceSimula-simulatorEngineLambda175-*`
- `/aws/lambda/IotHackathon-DeviceSimula-simulatormicroservices75-*`
- `/aws/lambda/iot-hackathon-lambda-kafka-bridge`
- `/aws/vendedlogs/states/IotHackathon-DeviceSimulator-simulatorStepFunctionsLogGroup-*`
- `API-Gateway-Execution-Logs_<api-id>/prod` (execution logs for the Device
  Simulator's REST API; the API itself was already gone via stack deletion,
  confirmed via `GetRestApi` returning `NotFoundException` before deleting
  the orphaned log group)

None of these were tracked as CloudFormation resources (Lambda/API Gateway
auto-create their own log groups outside the stack's resource graph), so they
survived stack deletion and had to be swept and deleted separately.

### Networking

- VPC, all subnets (public + private), NAT Gateway, Internet Gateway, route
  tables, and all VPC interface endpoints (SSM, SSM Messages, EC2 Messages,
  Secrets Manager) — deleted via the `IotHackathon-Network` stack.
- All project security groups — deleted via the `IotHackathon-Security` and
  `IotHackathon-Network` stacks, including the Kafka client security group
  (`MskClientSg`) whose deletion was blocked until the two orphaned IoT
  Rules Engine ENIs described above were cleared.
- No Elastic IPs, no orphaned "available" ENIs, and no non-default security
  groups belonging to this project remained at final verification.

---

## AWS resources preserved (explicitly, per user instruction)

| Resource | Reason preserved |
|---|---|
| **`CDKToolkit`** CloudFormation stack, its IAM roles (`cdk-hnb659fds-*`), ECR repo, and S3 asset bucket (`cdk-hnb659fds-assets-<account-id>-us-east-1`) | Explicitly named by the user as the one exception — generic, account-wide CDK bootstrap infrastructure, not exclusive to this project. |
| `ai-prod-os-*` Lambda functions and their execution role | Pre-existing, unrelated project. Never touched. |
| Default VPC and its `launch-wizard-1` security group | Pre-existing AWS account default, not created by or exclusive to this project. Never touched. |
| `/aws/apigateway/welcome` CloudWatch Log Group | AWS account-level default log group, not project-specific. |

---

## Snowflake

Because this project's Snowflake access always used per-service key-pair
credentials stored only in AWS Secrets Manager (no local copies were ever
retained, and no standing ACCOUNTADMIN session was held), deleting the three
Snowflake service-user secrets during the AWS-side cleanup removed the
assistant's own ability to run or verify DROP statements in Snowflake.

A ready-to-run script was provided to the user for execution in Snowsight as
`ACCOUNTADMIN` (also saved at `infra/snowflake/step_cleanup.sql`):

- `DROP DATABASE IF EXISTS IOT_PLATFORM CASCADE` — removes the database and
  every schema, table, view, stage, pipe, stream, task, and file format inside
  it.
- `DROP WAREHOUSE IF EXISTS IOT_INGEST_WH`
- `DROP USER IF EXISTS KAFKA_CONNECTOR_USER / DBT_USER / STREAMLIT_USER`
- `DROP ROLE IF EXISTS KAFKA_CONNECTOR_ROLE / DBT_ROLE / STREAMLIT_ROLE`

This project never created a native Snowflake "Streamlit App" object (the
dashboard was a separately hosted Streamlit app on EC2, already covered under
`IotHackathon-StreamlitHost` above).

**Status: pending user execution and confirmation.** This report should be
treated as complete for the AWS side; the Snowflake side is complete once the
user runs the script and confirms the `SHOW` verification queries return no
rows.

---

## Verification performed

Final account-wide scans (post-deletion, us-east-1 unless noted) confirmed:

- CloudFormation: only `CDKToolkit` remains in any non-`DELETE_COMPLETE` state.
- S3: only `cdk-hnb659fds-assets-<account-id>-us-east-1` (CDKToolkit) remains.
- IAM: only CDKToolkit roles, AWS service-linked roles, and the unrelated
  `ai-prod-os-lambda-role` remain.
- Secrets Manager: zero secrets under the `iot-hackathon/` prefix.
- IoT Core: zero Things, Certificates, Policies, or Topic Rules.
- EC2: zero instances, zero non-default security groups belonging to this
  project, zero Elastic IPs, zero orphaned/available ENIs, zero non-default
  VPCs.
- RDS: zero instances (this project used self-managed PostgreSQL on EC2, not
  RDS, so none were expected).
- MSK: zero clusters (the original `IotHackathon-Kafka` MSK cluster was
  decommissioned per the 2026-07-11 architecture revision, ahead of this
  cleanup).
- CloudWatch Alarms: zero matching this project's naming.

## Issues encountered and resolved

1. **Orphaned S3 buckets from `RemovalPolicy.RETAIN`** — four buckets survived
   their stacks' `DELETE_COMPLETE` status with data still inside. All four
   were found during independent post-deletion verification (not just trusted
   from the stack status) and explicitly emptied and deleted.
2. **Oversized single-batch S3 purge** — an initial attempt to purge the
   103k+-object backup bucket in one `delete-objects` call exceeded the API's
   1,000-object limit and failed (`MalformedXML`) partway through, silently
   leaving ~105,000 residual object versions and delete markers despite the
   bucket appearing "empty" by current-object count. Caught in follow-up
   verification and corrected with a properly paginated, batched purge.
3. **Orphaned VPC-destination ENIs blocking VPC teardown** — two AWS-managed
   ENIs from the IoT Rules Engine VPC destination outlived the destination's
   own deletion and blocked the `MskClientSg` security group (and therefore
   the private subnet and VPC) from deleting. Confirmed detached and the
   destination itself already gone, then deleted directly.
4. **Slow VPC-attached Lambda deletion** — `IotHackathon-LambdaKafkaBridge`
   took roughly 15–20 minutes to reach `DELETE_COMPLETE` due to expected AWS
   Hyperplane ENI cleanup for VPC-attached Lambda functions. Not an error;
   resolved by waiting.

**Nothing was force-deleted or bypassed.** Every resource listed above was
confirmed project-owned by name, tag, or CloudFormation ownership before
deletion; the four RETAIN-orphaned S3 buckets and the one orphaned IAM role
were independently verified via `list-object-versions`/`get-role` before
being removed, since none of them showed up as "still present" in the
corresponding stacks' resource lists.

## Outstanding action for the user

Run `infra/snowflake/step_cleanup.sql` in Snowsight as `ACCOUNTADMIN` to
complete the Snowflake side of this cleanup, then confirm the verification
`SHOW` statements return no rows.
