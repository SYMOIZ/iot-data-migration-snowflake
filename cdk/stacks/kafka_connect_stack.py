from pathlib import Path

from aws_cdk import Stack, CfnOutput, aws_ec2 as ec2, aws_iam as iam
from constructs import Construct


class KafkaConnectStack(Stack):
    """Self-managed Kafka Connect worker (Docker Compose on EC2) instead of MSK Connect.

    Runs Debezium's Kafka Connect distribution with: the Debezium JDBC Sink connector
    (iot-events -> PostgreSQL), the built-in Debezium Postgres source connector (used
    in Phase 2), and the Snowflake Kafka Connector staged for Phase 2. Authenticates to
    MSK with IAM (aws-msk-iam-auth), not a shared secret.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        sg_msk_client: ec2.SecurityGroup,
        msk_cluster_arn: str,
        msk_bootstrap_servers: str,
        db_secret,
        postgres_instance,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name")
        db_name = self.node.try_get_context("db_name")
        topic = self.node.try_get_context("kafka_topic")

        role = iam.Role(
            self,
            "KafkaConnectRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"),
            ],
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["kafka-cluster:Connect", "kafka-cluster:DescribeCluster"],
                resources=[msk_cluster_arn],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kafka-cluster:*Topic*",
                    "kafka-cluster:ReadData",
                    "kafka-cluster:WriteData",
                ],
                resources=[f"arn:aws:kafka:{self.region}:{self.account}:topic/{project}-msk/*"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["kafka-cluster:AlterGroup", "kafka-cluster:DescribeGroup"],
                resources=[f"arn:aws:kafka:{self.region}:{self.account}:group/{project}-msk/*"],
            )
        )
        db_secret.grant_read(role)

        template_path = Path(__file__).resolve().parents[2] / "ec2" / "kafka-connect-userdata.sh.tpl"
        userdata_template = template_path.read_text()
        userdata_script = (
            userdata_template.replace("{{AWS_REGION}}", self.region)
            .replace("{{MSK_BOOTSTRAP_BROKERS}}", msk_bootstrap_servers)
            .replace("{{DB_SECRET_ARN}}", db_secret.secret_arn)
            .replace("{{DB_NAME}}", db_name)
            .replace("{{POSTGRES_PRIVATE_IP}}", postgres_instance.instance_private_ip)
            .replace("{{KAFKA_TOPIC}}", topic)
        )
        user_data = ec2.UserData.custom(userdata_script)

        self.instance = ec2.Instance(
            self,
            "KafkaConnectInstance",
            instance_name=f"{project}-kafka-connect",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            instance_type=ec2.InstanceType("t3.large"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=sg_msk_client,
            role=role,
            user_data=user_data,
            # Containers need an extra IMDS hop to reach instance credentials (see UserData).
            http_put_response_hop_limit=2,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        30, volume_type=ec2.EbsDeviceVolumeType.GP3, encrypted=True
                    ),
                )
            ],
        )
        self.instance.node.add_dependency(postgres_instance)

        CfnOutput(self, "KafkaConnectInstanceId", value=self.instance.instance_id)
        CfnOutput(self, "KafkaConnectPrivateIp", value=self.instance.instance_private_ip)
        CfnOutput(
            self,
            "KafkaConnectRestApi",
            value=f"http://{self.instance.instance_private_ip}:8083 (reachable from bastion via SSM port-forward)",
        )
