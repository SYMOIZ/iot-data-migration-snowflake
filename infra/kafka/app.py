#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.kafka_broker_stack import KafkaBrokerStack
from stacks.kafka_connect_stack import KafkaConnectStack
from stacks.lambda_bridge_stack import LambdaKafkaBridgeStack

app = cdk.App()
env = cdk.Environment(account="<AWS_ACCOUNT_ID>", region="us-east-1")

KafkaBrokerStack(
    app,
    "IotHackathon-KafkaBroker",
    env=env,
    description=(
        "IoT Hackathon Phase 1 - self-managed Apache Kafka broker (KRaft mode, "
        "Docker Compose) on a dedicated EC2 instance. Replaces the earlier Amazon "
        "MSK approach per explicit architecture change. Imports the existing "
        "IotHackathon-Network stack's VPC/subnets/security groups; creates no "
        "VPC, subnet, or IAM resources of its own beyond this stack's instance role."
    ),
)

KafkaConnectStack(
    app,
    "IotHackathon-KafkaConnect",
    env=env,
    description=(
        "IoT Hackathon Phase 1 - Kafka Connect worker host (EC2 + Docker Compose), "
        "dedicated instance per approved implementation decision. Connects to the "
        "self-managed Kafka broker. No connectors configured in this stack."
    ),
)

LambdaKafkaBridgeStack(
    app,
    "IotHackathon-LambdaKafkaBridge",
    env=env,
    description=(
        "IoT Hackathon Phase 1 - Lambda bridge from AWS IoT Core to the self-managed "
        "Kafka broker (IoT Core -> Lambda -> Kafka), replacing the direct IoT Rule "
        "Kafka action approach (blocked by AWS IoT's TLS-only requirement)."
    ),
)

app.synth()
