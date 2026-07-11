#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.network_stack import NetworkStack
from stacks.security_stack import SecurityStack
from stacks.database_stack import DatabaseStack
from stacks.msk_stack import MskStack
from stacks.kafka_connect_stack import KafkaConnectStack
from stacks.iot_stack import IotStack

app = cdk.App()

account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
env = cdk.Environment(account=account, region=region)

tags = {"project": "iot-hackathon", "phase": "1", "managed-by": "cdk"}

network = NetworkStack(app, "IotHackathon-Network", env=env)
security = SecurityStack(app, "IotHackathon-Security", env=env)

database = DatabaseStack(
    app,
    "IotHackathon-Database",
    env=env,
    vpc=network.vpc,
    sg_postgres=network.sg_postgres,
    sg_bastion=network.sg_bastion,
    db_secret=security.db_secret,
)
database.add_dependency(network)
database.add_dependency(security)

msk = MskStack(
    app,
    "IotHackathon-Msk",
    env=env,
    vpc=network.vpc,
    sg_msk=network.sg_msk,
)
msk.add_dependency(network)

kafka_connect = KafkaConnectStack(
    app,
    "IotHackathon-KafkaConnect",
    env=env,
    vpc=network.vpc,
    sg_msk_client=network.sg_msk_client,
    msk_cluster_arn=msk.cluster.attr_arn,
    msk_bootstrap_servers=msk.bootstrap_brokers_sasl_iam,
    db_secret=security.db_secret,
    postgres_instance=database.postgres_instance,
)
kafka_connect.add_dependency(network)
kafka_connect.add_dependency(security)
kafka_connect.add_dependency(database)
kafka_connect.add_dependency(msk)

iot_stack = IotStack(
    app,
    "IotHackathon-Iot",
    env=env,
    vpc=network.vpc,
    sg_msk_client=network.sg_msk_client,
    msk_cluster_arn=msk.cluster.attr_arn,
    msk_bootstrap_servers=msk.bootstrap_brokers_sasl_iam,
    project_name_for_topic=app.node.try_get_context("project_name") + "-msk",
)
iot_stack.add_dependency(msk)

for stack in (network, security, database, msk, kafka_connect, iot_stack):
    for k, v in tags.items():
        cdk.Tags.of(stack).add(k, v)

app.synth()
