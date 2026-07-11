#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.database_stack import DatabaseStack

app = cdk.App()

DatabaseStack(
    app,
    "IotHackathon-Database",
    env=cdk.Environment(account="159412676011", region="us-east-1"),
    description=(
        "IoT Hackathon Phase 1 - Database Infrastructure (PostgreSQL EC2 + Bastion). "
        "Imports the existing IotHackathon-Network and IotHackathon-Security stacks; "
        "creates no VPC, subnet, IAM, Secrets Manager, or S3 resources of its own."
    ),
)

app.synth()
