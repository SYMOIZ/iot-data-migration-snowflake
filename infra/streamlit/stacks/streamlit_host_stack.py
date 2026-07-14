from aws_cdk import (
    Stack,
    Tags,
    CfnOutput,
    aws_ec2 as ec2,
    aws_iam as iam,
)
from constructs import Construct

# Existing resources from the already-deployed IotHackathon-Network stack.
# This stack IMPORTS the VPC and a pre-existing public subnet only - it never
# modifies IotHackathon-Network or IotHackathon-Security. It creates one new
# security group of its own (not part of either protected stack) scoped to a
# single inbound port, because the dashboard needs a public link and every
# other security group in this project (Bastion, Postgres, Kafka, MSK
# client) is deliberately "no inbound, SSM only".
VPC_ID = "<VPC_ID>"
AZ_1 = "us-east-1a"
AZ_2 = "us-east-1b"
PUBLIC_SUBNET_AZ1 = "<PUBLIC_SUBNET_AZ1>"
PUBLIC_SUBNET_AZ2 = "<PUBLIC_SUBNET_AZ2>"
PRIVATE_SUBNET_AZ1 = "<PRIVATE_SUBNET_AZ1>"
PRIVATE_SUBNET_AZ2 = "<PRIVATE_SUBNET_AZ2>"
DASHBOARD_PORT = 8501

USER_DATA = """#!/bin/bash
set -eux
exec > /var/log/user-data.log 2>&1
dnf update -y
dnf install -y python3-pip python3-devel gcc
touch /var/log/streamlit-host-bootstrap-complete
"""


class StreamlitHostStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        Tags.of(self).add("project", "iot-hackathon")
        Tags.of(self).add("phase", "1")
        Tags.of(self).add("managed-by", "cdk")

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "ImportedVpc",
            vpc_id=VPC_ID,
            availability_zones=[AZ_1, AZ_2],
            public_subnet_ids=[PUBLIC_SUBNET_AZ1, PUBLIC_SUBNET_AZ2],
            private_subnet_ids=[PRIVATE_SUBNET_AZ1, PRIVATE_SUBNET_AZ2],
        )

        dashboard_sg = ec2.SecurityGroup(
            self,
            "StreamlitDashboardSg",
            vpc=vpc,
            description="IoT Hackathon Streamlit dashboard - inbound HTTP dashboard port only",
            allow_all_outbound=True,
        )
        dashboard_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(DASHBOARD_PORT),
            "Streamlit dashboard (read-only analytics UI)",
        )

        instance_role = iam.Role(
            self,
            "StreamlitInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        instance = ec2.Instance(
            self,
            "StreamlitInstance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.SMALL
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[vpc.public_subnets[0]]),
            security_group=dashboard_sg,
            role=instance_role,
            require_imdsv2=True,
            associate_public_ip_address=True,
            user_data=ec2.UserData.custom(USER_DATA),
        )
        Tags.of(instance).add("Name", "iot-hackathon-streamlit-dashboard")

        CfnOutput(self, "StreamlitInstanceId", value=instance.instance_id)
        CfnOutput(self, "StreamlitPublicIp", value=instance.instance_public_ip)
        CfnOutput(
            self,
            "StreamlitDashboardUrl",
            value=f"http://{instance.instance_public_ip}:{DASHBOARD_PORT}",
        )
