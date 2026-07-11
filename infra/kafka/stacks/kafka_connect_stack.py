from aws_cdk import (
    Stack,
    Tags,
    CfnOutput,
    aws_ec2 as ec2,
    aws_iam as iam,
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
# Client-side security group: already has an 8083 rule labeled "Kafka Connect
# REST API" from BastionSg - this instance was clearly meant to use this SG.
MSK_CLIENT_SG_ID = "sg-028a6ec99e24e63cc"

# Private IP of the already-running Kafka broker instance (IotHackathon-KafkaBroker).
KAFKA_BROKER_BOOTSTRAP = "10.42.2.152:9092"

HOST_SETUP_USER_DATA = """#!/bin/bash
set -eux
exec > /var/log/user-data.log 2>&1

dnf update -y
# curl-minimal ships by default on AL2023 and conflicts with the full curl
# package - do not request curl separately (lesson learned on the broker host).
dnf install -y docker java-17-amazon-corretto-headless unzip

systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/libexec/docker/cli-plugins
curl -sL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \\
  -o /usr/libexec/docker/cli-plugins/docker-compose
chmod +x /usr/libexec/docker/cli-plugins/docker-compose

touch /var/log/host-setup-complete
"""


class KafkaConnectStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        Tags.of(self).add("project", "iot-hackathon")
        Tags.of(self).add("phase", "1")
        Tags.of(self).add("task", "1.3")
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
            "KafkaConnectInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        instance = ec2.Instance(
            self,
            "KafkaConnectInstance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.LARGE
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[vpc.private_subnets[0]]),
            security_group=msk_client_sg,
            role=role,
            user_data=ec2.UserData.custom(HOST_SETUP_USER_DATA),
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
        )
        Tags.of(instance).add("Name", "iot-hackathon-kafka-connect")

        CfnOutput(self, "KafkaConnectInstanceId", value=instance.instance_id)
        CfnOutput(self, "KafkaConnectPrivateIp", value=instance.instance_private_ip)
