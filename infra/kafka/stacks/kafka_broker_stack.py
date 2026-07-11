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
# Broker-side security group: already permits inbound 9092/9094/9098 from
# MskClientSg and BastionSg. This EC2 instance now plays the broker role
# that Amazon MSK would have played, so it uses this SG.
MSK_SG_ID = "sg-02b40d867975ba242"

# Fixed KRaft cluster ID (base64, 22 chars) - reserved for the later phase that
# actually deploys the Kafka container via Docker Compose. Not used in this
# stack's UserData, which only provisions the host (Docker/Compose/Java).
KRAFT_CLUSTER_ID = "MkU3OEVBNTcwNTJENDM2Qk"

HOST_SETUP_USER_DATA = """#!/bin/bash
set -eux
exec > /var/log/user-data.log 2>&1

dnf update -y
# Amazon Linux 2023 ships curl-minimal by default, which conflicts with the
# full "curl" package - the pre-installed curl-minimal binary already
# provides everything needed here, so it is not requested separately.
dnf install -y docker java-17-amazon-corretto-headless unzip

systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/libexec/docker/cli-plugins
curl -sL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \\
  -o /usr/libexec/docker/cli-plugins/docker-compose
chmod +x /usr/libexec/docker/cli-plugins/docker-compose

mkdir -p /opt/kafka

touch /var/log/host-setup-complete
"""


class KafkaBrokerStack(Stack):
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
        msk_sg = ec2.SecurityGroup.from_security_group_id(
            self, "ImportedMskSg", MSK_SG_ID, mutable=False
        )

        role = iam.Role(
            self,
            "KafkaBrokerInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        instance = ec2.Instance(
            self,
            "KafkaBrokerInstance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.LARGE
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[vpc.private_subnets[0]]),
            security_group=msk_sg,
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
        Tags.of(instance).add("Name", "iot-hackathon-kafka-broker")

        CfnOutput(self, "KafkaBrokerInstanceId", value=instance.instance_id)
        CfnOutput(self, "KafkaBrokerPrivateIp", value=instance.instance_private_ip)
