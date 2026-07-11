from pathlib import Path

from aws_cdk import Stack, CfnOutput, aws_ec2 as ec2, aws_iam as iam
from constructs import Construct


class DatabaseStack(Stack):
    """PostgreSQL EC2 (on-prem simulation, private subnet) + Bastion host (SSM only)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        sg_postgres: ec2.SecurityGroup,
        sg_bastion: ec2.SecurityGroup,
        db_secret,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name")
        db_name = self.node.try_get_context("db_name")
        pg_instance_type = self.node.try_get_context("postgres_instance_type")
        bastion_instance_type = self.node.try_get_context("bastion_instance_type")

        amzn_linux = ec2.MachineImage.latest_amazon_linux2023()

        # --- PostgreSQL EC2 role: SSM (no SSH key), read the one DB secret, CloudWatch agent ---
        pg_role = iam.Role(
            self,
            "PostgresRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"),
            ],
        )
        db_secret.grant_read(pg_role)

        template_path = Path(__file__).resolve().parents[2] / "ec2" / "postgres-userdata.sh.tpl"
        userdata_template = template_path.read_text()
        userdata_script = (
            userdata_template.replace("{{DB_SECRET_ARN}}", db_secret.secret_arn)
            .replace("{{AWS_REGION}}", self.region)
            .replace("{{DB_NAME}}", db_name)
            .replace("{{VPC_CIDR}}", vpc.vpc_cidr_block)
        )
        pg_user_data = ec2.UserData.custom(userdata_script)

        self.postgres_instance = ec2.Instance(
            self,
            "PostgresInstance",
            instance_name=f"{project}-postgres-onprem",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            instance_type=ec2.InstanceType(pg_instance_type),
            machine_image=amzn_linux,
            security_group=sg_postgres,
            role=pg_role,
            user_data=pg_user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        20, volume_type=ec2.EbsDeviceVolumeType.GP3, encrypted=True
                    ),
                )
            ],
        )

        # --- Bastion host: public subnet, SSM Session Manager only, no inbound SG rules ---
        bastion_role = iam.Role(
            self,
            "BastionRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )
        db_secret.grant_read(bastion_role)

        bastion_user_data = ec2.UserData.for_linux()
        bastion_user_data.add_commands(
            "dnf install -y postgresql15 jq",
        )

        self.bastion_instance = ec2.Instance(
            self,
            "BastionInstance",
            instance_name=f"{project}-bastion",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType(bastion_instance_type),
            machine_image=amzn_linux,
            security_group=sg_bastion,
            role=bastion_role,
            user_data=bastion_user_data,
        )

        CfnOutput(self, "PostgresInstanceId", value=self.postgres_instance.instance_id)
        CfnOutput(self, "PostgresPrivateIp", value=self.postgres_instance.instance_private_ip)
        CfnOutput(self, "BastionInstanceId", value=self.bastion_instance.instance_id)
