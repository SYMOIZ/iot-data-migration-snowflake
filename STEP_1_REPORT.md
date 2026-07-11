# STEP 1 Report — AWS Environment Verification & Cleanup Prep

**Date:** 2026-07-11
**Scope:** Verification and read-only discovery only. No resources were created or deleted in this step.

---

## 0. Architecture Confirmation

The repo (`symoiz/aws-hackathon`) contains only a placeholder `README.md`. No Architecture Diagram, SRS, or detailed README currently exist in-repo. The only design source available was the instructor's hackathon brief (uploaded `.docx`), whose approved pipeline matches the one given in this task:

```
AWS IoT Device Simulator → AWS IoT Core (MQTT) → Amazon MSK → Kafka Connect on EC2
→ PostgreSQL on EC2 → Debezium CDC → Kafka MSK (CDC topic) → Snowflake → dbt → Streamlit
```

No changes were made to this architecture. **Recommendation:** add the actual Architecture Diagram/SRS files to the repo before Step 2 so there's an in-repo source of truth.

---

## 1. Environment Status

| Check | Result |
|---|---|
| AWS CLI | Installed — `aws-cli/2.35.21 Python/3.14.6 Linux/6.18.5` |
| Credential Status | **Valid**, after fix (see below) |
| AWS Account | `159412676011` |
| IAM Identity | `arn:aws:iam::159412676011:user/claude` (UserId `AIDASKHN4MWV3KNMAB57U`) |
| Region | `us-east-1` |

**Credential note:** the first `aws sts get-caller-identity` attempt failed with `InvalidClientTokenId`. Root cause was **not** a bad key — this sandbox has its own `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` environment variables set (belonging to the outbound network proxy), which take precedence over the CLI profile. Once the AWS CLI calls explicitly excluded those environment variables, the uploaded key authenticated successfully on the first try.

---

## 2. CloudFormation

| Stack | Status | Created | Notes |
|---|---|---|---|
| `IotHackathon-Network` | CREATE_COMPLETE | 2026-07-11 18:14 UTC | VPC + networking for this project — **live** |
| `IotHackathon-Security` | CREATE_COMPLETE | 2026-07-11 18:16 UTC | S3 backup bucket + Secrets Manager secret — **live** |
| `IotHackathon-Database` | DELETE_COMPLETE | 2026-07-11 18:17 UTC | Already deleted (Bastion + PostgreSQL EC2). Left two `terminated` EC2 instances visible in the API — this is normal AWS behavior; they auto-purge from `describe-instances` output within ~1 hour and cost nothing. |
| `CDKToolkit` | CREATE_COMPLETE | 2026-07-11 18:02 UTC | CDK bootstrap stack (IAM roles, ECR repo, S3 staging bucket). Not project-specific — shared infra needed by **any** future CDK deployment in this account. |

No stacks in `ROLLBACK_COMPLETE` or `DELETE_FAILED`.

### Resources inside the live stacks

**`IotHackathon-Security`**
- S3 bucket: `iot-hackathon-iot-backup-159412676011-us-east-1`
- Secrets Manager secret: `iot-hackathon/postgres/credentials`

**`IotHackathon-Network`**
- VPC `vpc-06802348bb7d24fd8` (10.42.0.0/16, tagged `iot-hackathon-vpc`)
- 4 subnets (2 public, 2 private), 4 route tables + associations, 1 Internet Gateway, 1 NAT Gateway, 1 associated Elastic IP (`54.236.189.170`)
- 4 security groups (Bastion, MskClient, Msk, Postgres) + ingress rules
- 5 VPC interface/gateway endpoints (EC2 Messages, S3, Secrets Manager, SSM, SSM Messages) + their security groups
- 9 ENIs, all belonging to the NAT Gateway and the 4 interface endpoints above (not orphans)

---

## 3. Existing Resources — Classified

### Project Resources (this hackathon — `iot-hackathon`)
| Resource | Notes |
|---|---|
| CFN stacks `IotHackathon-Network`, `IotHackathon-Security` | Live, CREATE_COMPLETE |
| VPC `vpc-06802348bb7d24fd8` + all subnets/route tables/IGW/NAT/SGs/endpoints/ENIs listed above | All part of `IotHackathon-Network` |
| S3 bucket `iot-hackathon-iot-backup-159412676011-us-east-1` | Part of `IotHackathon-Security` |
| Secrets Manager `iot-hackathon/postgres/credentials` | Part of `IotHackathon-Security` |
| EC2 `i-0508ea1f58a8d67c6` (`iot-hackathon-bastion`) — **terminated** | Leftover from deleted `IotHackathon-Database` stack; tagged `project=iot-hackathon` |
| EC2 `i-0d0bd671c9873e466` (`iot-hackathon-postgres-onprem`) — **terminated** | Same as above |
| Elastic IP `54.236.189.170` (`eipalloc-089326ddbfb5b0222`) | Attached to the live NAT Gateway — in use, part of `IotHackathon-Network` |

### Non-Project Resources (pre-existing, unrelated — **not touched**)
| Resource | Notes |
|---|---|
| Default VPC `vpc-00316835b395c271c` | Standard AWS default VPC |
| IAM role `ai-prod-os-lambda-role` | Created 2026-07-11 07:12 UTC — hours before this project's deployment; belongs to a different app |
| IAM role `s3` | Created 2026-04-05 — unrelated, pre-existing |
| IAM role `Symoiz` | Created 2026-02-08 — unrelated, pre-existing |
| 8 CloudWatch log groups `/aws/lambda/ai-prod-os-*` | Belong to the unrelated `ai-prod-os` app |
| CDKToolkit stack + its IAM roles/ECR repo/S3 staging bucket | Not project-specific; shared CDK bootstrap infra needed for future deployments in this account — recommend **keeping** |

### Unknown / Ambiguous Resources (flagged — **not touched, needs your decision**)
| Resource | Notes |
|---|---|
| Elastic IP `52.204.202.43` (`eipalloc-047d130fa49889ef2`) | Tagged `Name=MSK-VPC-eip-us-east-1a`. Unassociated (not attached to anything). Name suggests MSK-related infra but doesn't match the `iot-hackathon` tagging convention used by the current stacks — could be an earlier/differently-named attempt at this same project, or something unrelated. |
| Elastic IP `3.215.14.16` (`eipalloc-0ebb8b986adff4b85`) | Tagged `Name=msk-demo-vpc-main-eip-us-east-1a`. Unassociated. Same ambiguity as above. |
| Elastic IP `54.210.22.122` (`eipalloc-0aed86c128e756d60`) | **No tags at all.** Unassociated. Cannot determine origin. |

All three unknown EIPs are currently **unattached**, which means AWS is billing for idle Elastic IPs on all three. I have not deleted them since I can't confirm they belong to this project — flagging per your "never delete unknown resources automatically" instruction.

No MSK clusters, no EBS volumes, no EBS snapshots currently exist in the account.

---

## 4. Cleanup Plan (proposed — awaiting your approval, nothing deleted yet)

1. **Ask you to confirm** the three unknown Elastic IPs — keep, delete, or investigate further (e.g., check billing/CloudTrail for their creation history) before any action.
2. If you approve full teardown of the current partial deployment (so Step 2 starts from a true blank slate):
   - Delete stack `IotHackathon-Security` (removes S3 backup bucket + Secrets Manager secret)
   - Delete stack `IotHackathon-Network` (removes VPC, subnets, IGW, NAT Gateway, EIP `54.236.189.170`, security groups, endpoints, route tables) — this releases the NAT Gateway's EIP.
   - Leave `CDKToolkit` in place (shared bootstrap, reusable by Step 2)
   - The two terminated EC2 instances need no action — they will disappear from the API on their own.
3. If you'd rather **keep** the current `IotHackathon-Network`/`IotHackathon-Security` stacks as the foundation for Step 2 instead of tearing them down and redeploying, that's also viable since both are healthy (`CREATE_COMPLETE`) — let me know which you prefer.

**Nothing will be deleted until you explicitly approve a specific list.**

---

## 5. Potential Risks

- The three unassociated Elastic IPs are actively costing money regardless of what we decide about deletion — flagging for prompt attention.
- If `IotHackathon-Network` is deleted, anything still depending on its VPC endpoints (none currently, since Database/MSK/Kafka Connect were never deployed) would break — currently safe to delete if you choose that path.
- No `DELETE_FAILED` stacks or stuck resources were found — cleanup, if approved, should proceed without manual intervention.

---

## 6. Next Step

Awaiting your approval on:
1. What to do with the three unknown Elastic IPs.
2. Whether to tear down `IotHackathon-Network` + `IotHackathon-Security` for a clean slate, or keep them as the Step 2 foundation.

**Step 2 (deployment) will not start until you explicitly approve.**
