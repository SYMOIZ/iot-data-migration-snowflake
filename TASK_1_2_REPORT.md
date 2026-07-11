# Task 1.2 Report — AWS IoT Device Simulator + AWS IoT Core + MQTT

**Date:** 2026-07-11
**Status:** ✅ Automated portion complete and verified end-to-end. Manual portion (console configuration) documented below and left for the user, as specified.
**Scope:** Device Simulator infrastructure, IoT Policy/Thing/Certificate, MQTT topic `iot-events`, IoT Rule. **No MSK, no Kafka Connect, no PostgreSQL, no Snowflake** — all deferred to Task 1.3+ per the hackathon spec boundary.

---

## 1. What Was Automated

### 1a. AWS IoT Device Simulator (CloudFormation)

Deployed the official AWS Solutions "IoT Device Simulator" (SO0041) via CloudFormation.

**Important finding before deploying:** this solution was **deprecated by AWS on January 29, 2025** (repo now read-only, no further updates). Its published template pins all 3 Lambda functions to `Runtime: nodejs18.x`, and AWS blocked *creation* of new Lambda functions on nodejs18.x starting **October 1, 2025**. Deploying the template unmodified would have failed partway through stack creation.

**Fix applied (minimal, architecture-preserving):** downloaded the official template directly from AWS's `solutions-reference` S3 bucket, changed `Runtime: nodejs18.x` → `Runtime: nodejs20.x` on exactly the 3 Lambda function resources (verified via diff — no other lines touched), uploaded the patched template privately (via a short-lived presigned S3 URL, not a public object), and deployed with `--capabilities CAPABILITY_IAM`.

**Result:** `IotHackathon-DeviceSimulator` stack — `CREATE_COMPLETE`, 72 resources (Cognito User Pool + Identity Pool, API Gateway, 3 Lambda functions, 2 DynamoDB tables, 3 S3 buckets, CloudFront distribution, Step Functions state machine, Location Service map/place index, IAM roles/policies, CloudWatch alarms/log groups).

| Output | Value |
|---|---|
| Console URL | https://d1tlpcp0lb0gga.cloudfront.net |
| Cognito User Pool ID | `us-east-1_W0PK9Zc5k` |
| Admin/login email | `symoiz.dev@gmail.com` (per user confirmation; Cognito sends the invite/temp-password email here) |
| API Endpoint | https://l6uzpgke8c.execute-api.us-east-1.amazonaws.com/prod |

### 1b. AWS IoT Core resources

| Resource | Detail |
|---|---|
| IoT Policy | `iot-hackathon-device-policy` — allows `iot:Connect`, `iot:Publish`/`RetainPublish` and `iot:Subscribe`/`Receive` scoped to the `iot-events` topic only |
| IoT Thing | `iot-hackathon-wearable-001` — representative device identity |
| Certificate | Created, set **ACTIVE**, attached to the Thing and the policy attached to the certificate (standard Thing → Certificate → Policy chain) |
| MQTT topic | `iot-events` (implicit — AWS IoT topics don't require pre-creation; established by policy scope + rule + successful publish, see §2) |

### 1c. IoT Rule

- Name: `iot_hackathon_iot_events_rule`
- SQL: `SELECT * FROM 'iot-events'`
- Action: **CloudWatch Logs** (placeholder — target `/aws/iotrule/iot-hackathon-iot-events`, via a scoped IAM role `iot-hackathon-iot-rule-role`)
- **This is intentional and matches the task boundary**: Task 1.2 explicitly excludes MSK. The rule exists and is proven to work (§2); its action will be updated to add a Kafka action once Amazon MSK exists in Task 1.3, exactly as the hackathon doc anticipates ("if the direct integration isn't available in your setup, this routing will be completed in the next Kafka task").

## 2. Verification Performed

Published a test message matching the required payload shape directly to the `iot-events` topic via `aws iot-data publish`, then confirmed the IoT Rule routed it:

```json
{"device_id":"device-001","latitude":24.8607,"longitude":67.0011,"temperature":29.5,"humidity":62,"timestamp":"2026-07-11T19:47:00Z"}
```

Result — the exact payload appeared in CloudWatch Logs (`/aws/iotrule/iot-hackathon-iot-events`) within seconds, confirming: topic routing works, the rule SQL matches, the rule's IAM role has correct permissions, and the payload shape is compatible end-to-end. This is equivalent proof to using the IoT Core MQTT Test Client.

## 3. What Requires Manual Configuration (per hackathon spec — not automatable)

These steps require interactive login through the Cognito web console and are left for you:

1. **Check `symoiz.dev@gmail.com`** for the Cognito invitation email containing a temporary password.
2. **Open the Console URL:** https://d1tlpcp0lb0gga.cloudfront.net and sign in (you'll be prompted to set a permanent password on first login).
3. **Device Types → Create Device Type:**
   - Name: `WearableSensor`
   - Payload attributes: `device_id` (String), `latitude` (Float), `longitude` (Float), `timestamp` (Timestamp), `temperature` (Float), `humidity` (Float)
4. **Simulations → Create Simulation:**
   - Name: `WearableDemo`
   - Devices: `5`
   - Publish interval: `5` seconds
   - Topic: `iot-events` (matches the IoT Rule already listening on this topic)
5. **Start the simulation** and confirm in the AWS IoT Core MQTT Test Client (or `/aws/iotrule/iot-hackathon-iot-events` log group) that messages are flowing from all 5 simulated devices.

## 4. Deliverables Checklist

| Deliverable | Status |
|---|---|
| AWS IoT Device Simulator deployed | ✅ Automated |
| Device Type created | ⏳ Manual (instructions above) |
| Payload configured | ⏳ Manual (instructions above) |
| 5 virtual devices running | ⏳ Manual (instructions above) |
| MQTT topic publishing | ✅ Verified (test publish + rule routing) |
| IoT Core configured (Policy, Thing, Certificate, Rule) | ✅ Automated |

## 5. Resources Created This Task

- CloudFormation stack: `IotHackathon-DeviceSimulator`
- IoT Policy: `iot-hackathon-device-policy`
- IoT Thing: `iot-hackathon-wearable-001` + 1 certificate (active, attached)
- IoT Rule: `iot_hackathon_iot_events_rule`
- IAM role: `iot-hackathon-iot-rule-role` (CloudWatch Logs write, scoped to one log group)
- CloudWatch Log Group: `/aws/iotrule/iot-hackathon-iot-events`

No changes were made to `IotHackathon-Network`, `IotHackathon-Security`, or `IotHackathon-Database`.

## 6. Next Step

Task 1.2's automated portion is complete and verified. Once you complete the manual console steps (§3) and confirm 5 devices are publishing, Task 1.3 (Amazon MSK + Kafka Connect + JDBC Sink + Secrets Manager) is next — **not started**, awaiting your approval.
