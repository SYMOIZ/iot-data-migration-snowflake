#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.msk_stack import MskStack
from stacks.kafka_connect_stack import KafkaConnectStack

app = cdk.App()
env = cdk.Environment(account="159412676011", region="us-east-1")

msk_stack = MskStack(
    app,
    "IotHackathon-Kafka",
    env=env,
    description=(
        "IoT Hackathon Phase 1 - Amazon MSK cluster. Imports the existing "
        "IotHackathon-Network stack's VPC/subnets/security groups; creates no "
        "VPC, subnet, or IAM resources of its own beyond the MSK broker log group."
    ),
)

# Deployed in a second pass, after the MSK cluster is ACTIVE and its bootstrap
# brokers + cluster ARN are known (passed via CDK context: -c bootstrapBrokers=...
# -c clusterArn=...). Omitted from synth/deploy until that context is supplied so
# `cdk deploy IotHackathon-Kafka` alone doesn't try to touch this stack.
bootstrap_brokers = app.node.try_get_context("bootstrapBrokers")
cluster_arn = app.node.try_get_context("clusterArn")
if bootstrap_brokers and cluster_arn:
    KafkaConnectStack(
        app,
        "IotHackathon-KafkaConnect",
        env=env,
        bootstrap_brokers=bootstrap_brokers,
        cluster_arn=cluster_arn,
        description=(
            "IoT Hackathon Phase 1 - Kafka Connect worker (EC2 + Docker Compose), "
            "connecting to the existing IotHackathon-Kafka MSK cluster via IAM auth. "
            "No connectors are configured in this stack."
        ),
    )

app.synth()
