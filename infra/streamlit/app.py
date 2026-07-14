#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.streamlit_host_stack import StreamlitHostStack

app = cdk.App()

StreamlitHostStack(
    app,
    "IotHackathon-StreamlitHost",
    env=cdk.Environment(account="<AWS_ACCOUNT_ID>", region="us-east-1"),
    description=(
        "IoT Hackathon Phase 1 - Streamlit dashboard host (dedicated public EC2 "
        "instance + its own security group). Imports the existing "
        "IotHackathon-Network VPC/public subnet only; creates no VPC, IAM "
        "roles beyond its own instance role, or Secrets Manager resources."
    ),
)

app.synth()
