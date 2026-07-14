# Security Model

The security posture is uniform across the stack. This documents the model, the
incidents that occurred during the build, and the lessons applied.

---

## Principles

1. **No SSH anywhere.** Every EC2 instance is administered through **SSM
   Session Manager**. Instances have `AmazonSSMManagedInstanceCore` and **no
   key pair**. This is what the VPC interface endpoints (SSM, SSM Messages,
   EC2 Messages) exist for.
2. **No public IPs** except the Streamlit dashboard host (which needs a
   browsable URL and gets its own isolated security group).
3. **No static passwords.** Credentials live in **AWS Secrets Manager**;
   Snowflake uses **RSA key‑pair** authentication. Connector configs reference
   secrets via `${secretsManager:…}`, never literals.
4. **Least privilege.** Each service has its own IAM role and its own Snowflake
   role, scoped to exactly what it needs (see
   [architecture/design-decisions.md](../architecture/design-decisions.md)).
5. **Nothing sensitive in the repo.** Only public keys and Secrets Manager
   *references* are committed. Environment‑specific identifiers are placeholders
   (see [reference/configuration-values.md](../reference/configuration-values.md)).

## Secrets inventory

| Secret | Consumer | Auth |
|---|---|---|
| `iot-hackathon/postgres/credentials` | database bootstrap | password (Secrets Manager only) |
| `iot-hackathon/postgres/iot_platform-credentials` | JDBC Sink, Debezium | password (Secrets Manager only) |
| `iot-hackathon/snowflake/kafka-connector-key` | Snowflake Sink | RSA private key |
| `iot-hackathon/snowflake/dbt-key` | dbt | RSA private key |
| `iot-hackathon/snowflake/streamlit-key` | Streamlit | RSA private key |

Private keys are written to instance disk only when needed, at mode `600`, and
scratch copies are securely deleted after use.

---

## Incidents during the build (and remediations)

Documented in full for transparency. Both were self‑detected and remediated
before any further work.

### 1. PostgreSQL password echoed to a log

`set -x` shell tracing was active around a `psql -v dbpass=…` invocation,
writing the plaintext password into `/var/log/…` (and into a captured command
output). **Remediation:** rotated the secret to a fresh 32‑char value; moved
the password inside the SQL heredoc body (never on a traced command line);
redacted the log. The leaked value was never applied to a live credential.

### 2. Snowflake private key printed by a diagnostic script

A redaction fallback used string‑matching (`grep "BEGIN\|PRIVATE"`) that missed
an already‑stripped key body, printing the private key into a command output.
**Remediation:** generated a brand‑new key pair immediately; updated the
Secrets Manager secret; rotated the Snowflake user's `RSA_PUBLIC_KEY`; paused
until confirmed. The exposed key was never used for an authenticated
connection.

**Lesson applied:** never rely on string‑matching to redact secrets. Parse
responses as structured data and explicitly remove the sensitive field before
printing.

---

## Known, accepted limitations

- **Kafka Connect REST API exposes literal config.** Using
  `${secretsManager:…}` references keeps passwords out of the stored config;
  network access to `8083` is restricted to the Bastion/client security groups.
- **Single‑broker Kafka** (replication factor 1) — no HA, accepted for scope.
- **Plaintext Kafka listener** inside the VPC — acceptable because it's not
  network‑exposed and is the reason the Lambda bridge exists (IoT's native
  Kafka action requires TLS).

---

## Repo hygiene

- `.gitignore` excludes `cdk.out/`, `.venv/`, `__pycache__/`,
  `.streamlit/secrets.toml`, and dbt `target/`.
- Only public keys, `*.example` templates, and `${secretsManager:…}`
  references are committed. A full scan for account ids, private URLs, keys,
  and passwords is part of finalizing the repo.
