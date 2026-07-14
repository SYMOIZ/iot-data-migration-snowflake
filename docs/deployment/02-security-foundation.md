# 02 · Security Foundation

**Stack:** `IotHackathon-Security` · **Purpose:** the S3 raw‑backup bucket and
the Secrets Manager secret used by the database. Created once; imported (never
modified) by later stages.

---

## What to create

| Resource | Value |
|---|---|
| S3 bucket | `iot-hackathon-iot-backup-<AWS_ACCOUNT_ID>-us-east-1` |
| Secrets Manager secret | `iot-hackathon/postgres/credentials` |

---

## Console steps

### S3 backup bucket

1. **S3 → Create bucket.** Name it
   `iot-hackathon-iot-backup-<AWS_ACCOUNT_ID>-us-east-1` (bucket names are
   global, so the account id keeps it unique), region `us-east-1`.
2. Keep **Block all public access = ON**. Enable default encryption
   (SSE‑S3). Create.

This bucket is the destination for the Kafka S3 Sink connector in
[step 10](./10-s3-sink-connector.md).

### Database secret

1. **Secrets Manager → Store a new secret → Other type of secret.**
2. Add key/value pairs for the PostgreSQL credentials (e.g. `username`,
   `password`, `dbname`). Generate a strong password.
3. Name it `iot-hackathon/postgres/credentials`. Store.
4. Record the secret **ARN** (including its random `-<SUFFIX>`) for the
   database stage.

> Additional secrets (`iot-hackathon/postgres/iot_platform-credentials`, and
> the three Snowflake key secrets) are created later, in their respective
> steps.

---

## Verification

- **S3**: the bucket exists, is empty, and public access is blocked.
- **Secrets Manager**: the secret exists; "Retrieve secret value" shows your
  keys. The database instance will read it at boot using its IAM role.

## Why

- The bucket is provisioned up front so the S3 Sink connector has a fixed,
  known destination.
- Storing credentials in Secrets Manager (rather than in code or user data)
  is what lets every instance fetch secrets at runtime via its IAM role, with
  nothing sensitive committed to the repo.

---

Next: [03 · IoT Device Simulator](./03-iot-device-simulator.md)
