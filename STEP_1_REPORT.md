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

### Elastic IP Investigation (approved by user 2026-07-11 — not deleted, awaiting explicit delete approval)

Each of the three unassociated EIPs was checked against every possible attachment point: NAT Gateway, EC2 instance (including terminated), Classic/ALB/NLB Load Balancer, and ENI.

| EIP | Public IP | Tag | NAT GW | EC2 | Load Balancer | ENI | Verdict |
|---|---|---|---|---|---|---|---|
| `eipalloc-047d130fa49889ef2` | 52.204.202.43 | `MSK-VPC-eip-us-east-1a` | Not attached | Not attached | None found | Not attached | **Safe to delete** — not required by `iot-hackathon` |
| `eipalloc-0ebb8b986adff4b85` | 3.215.14.16 | `msk-demo-vpc-main-eip-us-east-1a` | Not attached | Not attached | None found | Not attached | **Safe to delete** — not required by `iot-hackathon` |
| `eipalloc-0aed86c128e756d60` | 54.210.22.122 | *(none)* | Not attached | Not attached | None found | Not attached | **Safe to delete** — not required by `iot-hackathon` |

Supporting checks:
- Account has exactly **one** NAT Gateway (`nat-0188c9bb9b99819e5`, part of the retained `IotHackathon-Network` stack), using a different EIP (`54.236.189.170`) — already in use, unrelated to the three above.
- **Zero** Classic ELBs and **zero** ALB/NLBs exist in the account.
- No EC2 instance (terminated or otherwise) holds any of these three public IPs.
- No ENI is associated with any of these three public IPs.

**Conclusion:** all three are genuinely orphaned and not required by the current or planned `iot-hackathon` deployment. Marked **safe to delete**, but per instruction **not deleted** — awaiting explicit approval.

No MSK clusters, no EBS volumes, no EBS snapshots currently exist in the account.

---

## 4. Cleanup Plan (decision recorded — nothing deleted yet)

**User decision (2026-07-11):** `IotHackathon-Network` and `IotHackathon-Security` are part of the approved architecture and will be **reused** in Step 2 — not deleted. Unrelated resources are not to be touched.

Remaining action, pending final go-ahead:
- Delete the three orphaned, unassociated Elastic IPs identified above (`52.204.202.43`, `3.215.14.16`, `54.210.22.122`) — confirmed not attached to any NAT Gateway, EC2 instance, Load Balancer, or ENI, and not required by this project.
- The two terminated EC2 instances (leftover from the already-deleted `IotHackathon-Database` stack) need no action — they will disappear from the API on their own.
- `CDKToolkit` stays in place as shared CDK bootstrap infra for Step 2.

**No deletions will occur until you give explicit approval.**

---

## 5. Potential Risks

- The three unassociated Elastic IPs are actively costing money while the deletion decision is pending — flagging for prompt attention.
- `IotHackathon-Network` and `IotHackathon-Security` are being retained per your instruction; no risk introduced since nothing further was deployed on top of them (no Database/MSK/Kafka Connect exists yet).
- No `DELETE_FAILED` stacks or stuck resources were found.

---

## 6. Next Step

`IotHackathon-Network` and `IotHackathon-Security` are confirmed as the foundation for Step 2 — no teardown needed there.

Awaiting your explicit approval to delete the three orphaned Elastic IPs (`52.204.202.43`, `3.215.14.16`, `54.210.22.122`). Once approved, that is the only cleanup action left before Step 1 is fully closed out.

**Step 2 (deployment) will not start until you explicitly approve.**
