import os

from aws_cdk import (
    Stack,
    Tags,
    CfnOutput,
    Duration,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct

# Existing resources from the already-deployed IotHackathon-Network stack.
# This stack IMPORTS them only - it never creates or manages VPC, subnet,
# or security group resources.
VPC_ID = "vpc-06802348bb7d24fd8"
AZ_1 = "us-east-1a"
AZ_2 = "us-east-1b"
PRIVATE_SUBNET_AZ1 = "subnet-0b48a9b72ff904555"
PRIVATE_SUBNET_AZ2 = "subnet-0f7951f481e8144a5"
# Client-side security group: the Kafka broker's MskSg already permits
# inbound 9092 from this group (same pattern used by Kafka Connect).
MSK_CLIENT_SG_ID = "sg-028a6ec99e24e63cc"

KAFKA_BOOTSTRAP_SERVERS = "10.42.2.152:9092"
KAFKA_TOPIC = "iot-events"

LAMBDA_CODE_DIR = os.path.join(os.path.dirname(__file__), "..", "lambda_bridge")


class LambdaKafkaBridgeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        Tags.of(self).add("project", "iot-hackathon")
        Tags.of(self).add("phase", "1")
        Tags.of(self).add("task", "lambda-kafka-bridge")
        Tags.of(self).add("managed-by", "cdk")

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "ImportedVpc",
            vpc_id=VPC_ID,
            availability_zones=[AZ_1, AZ_2],
            private_subnet_ids=[PRIVATE_SUBNET_AZ1, PRIVATE_SUBNET_AZ2],
        )
        msk_client_sg = ec2.SecurityGroup.from_security_group_id(
            self, "ImportedMskClientSg", MSK_CLIENT_SG_ID, mutable=False
        )

        role = iam.Role(
            self,
            "LambdaKafkaBridgeRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )

        fn = lambda_.Function(
            self,
            "LambdaKafkaBridge",
            function_name="iot-hackathon-lambda-kafka-bridge",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(LAMBDA_CODE_DIR),
            role=role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[vpc.private_subnets[0]]),
            security_groups=[msk_client_sg],
            environment={
                "KAFKA_BOOTSTRAP_SERVERS": KAFKA_BOOTSTRAP_SERVERS,
                "KAFKA_TOPIC": KAFKA_TOPIC,
            },
            timeout=Duration.seconds(30),
            memory_size=256,
        )

        CfnOutput(self, "LambdaFunctionArn", value=fn.function_arn)
        CfnOutput(self, "LambdaFunctionName", value=fn.function_name)
