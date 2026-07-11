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
MSK_CLIENT_SG_ID = "sg-028a6ec99e24e63cc"

CONNECT_GROUP_ID = "iot-hackathon-connect-cluster"


class KafkaConnectStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bootstrap_brokers: str,
        cluster_arn: str,
        **kwargs,
    ) -> None:
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

        topic_arn = cluster_arn.replace(":cluster/", ":topic/") + "/*"
        group_arn = cluster_arn.replace(":cluster/", ":group/") + "/*"

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
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["kafka-cluster:Connect", "kafka-cluster:DescribeCluster"],
                resources=[cluster_arn],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kafka-cluster:CreateTopic",
                    "kafka-cluster:DescribeTopic",
                    "kafka-cluster:AlterTopic",
                    "kafka-cluster:WriteData",
                    "kafka-cluster:ReadData",
                ],
                resources=[topic_arn],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["kafka-cluster:AlterGroup", "kafka-cluster:DescribeGroup"],
                resources=[group_arn],
            )
        )

        user_data_script = f"""#!/bin/bash
set -eux
exec > /var/log/user-data.log 2>&1

dnf update -y
dnf install -y docker java-17-amazon-corretto-headless unzip curl

systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/libexec/docker/cli-plugins
curl -sL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \\
  -o /usr/libexec/docker/cli-plugins/docker-compose
chmod +x /usr/libexec/docker/cli-plugins/docker-compose

mkdir -p /opt/kafka-connect
cd /opt/kafka-connect

cat > Dockerfile << 'EODOCKERFILE'
FROM confluentinc/cp-kafka-connect:7.6.1
USER root
RUN mkdir -p /usr/share/java/kafka && \\
    curl -sL -o /usr/share/java/kafka/aws-msk-iam-auth.jar \\
    https://github.com/aws/aws-msk-iam-auth/releases/download/v2.2.0/aws-msk-iam-auth-2.2.0-all.jar
EODOCKERFILE

cat > docker-compose.yml << EOCOMPOSE
services:
  kafka-connect:
    build: .
    image: iot-hackathon-kafka-connect:local
    container_name: kafka-connect
    restart: unless-stopped
    network_mode: host
    environment:
      CONNECT_BOOTSTRAP_SERVERS: "{bootstrap_brokers}"
      CONNECT_GROUP_ID: "{CONNECT_GROUP_ID}"
      CONNECT_CONFIG_STORAGE_TOPIC: "connect-configs"
      CONNECT_OFFSET_STORAGE_TOPIC: "connect-offsets"
      CONNECT_STATUS_STORAGE_TOPIC: "connect-status"
      CONNECT_CONFIG_STORAGE_REPLICATION_FACTOR: "2"
      CONNECT_OFFSET_STORAGE_REPLICATION_FACTOR: "2"
      CONNECT_STATUS_STORAGE_REPLICATION_FACTOR: "2"
      CONNECT_KEY_CONVERTER: "org.apache.kafka.connect.json.JsonConverter"
      CONNECT_VALUE_CONVERTER: "org.apache.kafka.connect.json.JsonConverter"
      CONNECT_KEY_CONVERTER_SCHEMAS_ENABLE: "false"
      CONNECT_VALUE_CONVERTER_SCHEMAS_ENABLE: "false"
      CONNECT_INTERNAL_KEY_CONVERTER: "org.apache.kafka.connect.json.JsonConverter"
      CONNECT_INTERNAL_VALUE_CONVERTER: "org.apache.kafka.connect.json.JsonConverter"
      CONNECT_REST_ADVERTISED_HOST_NAME: "127.0.0.1"
      CONNECT_PLUGIN_PATH: "/usr/share/java,/usr/share/confluent-hub-components"
      CONNECT_SECURITY_PROTOCOL: "SASL_SSL"
      CONNECT_SASL_MECHANISM: "AWS_MSK_IAM"
      CONNECT_SASL_JAAS_CONFIG: "software.amazon.msk.auth.iam.IAMLoginModule required;"
      CONNECT_SASL_CLIENT_CALLBACK_HANDLER_CLASS: "software.amazon.msk.auth.iam.IAMClientCallbackHandler"
      CONNECT_PRODUCER_SECURITY_PROTOCOL: "SASL_SSL"
      CONNECT_PRODUCER_SASL_MECHANISM: "AWS_MSK_IAM"
      CONNECT_PRODUCER_SASL_JAAS_CONFIG: "software.amazon.msk.auth.iam.IAMLoginModule required;"
      CONNECT_PRODUCER_SASL_CLIENT_CALLBACK_HANDLER_CLASS: "software.amazon.msk.auth.iam.IAMClientCallbackHandler"
      CONNECT_CONSUMER_SECURITY_PROTOCOL: "SASL_SSL"
      CONNECT_CONSUMER_SASL_MECHANISM: "AWS_MSK_IAM"
      CONNECT_CONSUMER_SASL_JAAS_CONFIG: "software.amazon.msk.auth.iam.IAMLoginModule required;"
      CONNECT_CONSUMER_SASL_CLIENT_CALLBACK_HANDLER_CLASS: "software.amazon.msk.auth.iam.IAMClientCallbackHandler"
      CONNECT_LOG4J_ROOT_LOGLEVEL: "INFO"
EOCOMPOSE

docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d

touch /var/log/kafka-connect-bootstrap-complete
"""

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
            user_data=ec2.UserData.custom(user_data_script),
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
        # Docker containers add a network hop to the instance metadata service;
        # the aws-msk-iam-auth library inside the container needs IMDS access to
        # pick up the instance role's credentials, so the hop limit must be raised
        # above the default of 1. Set directly on the CfnInstance (no LaunchTemplate
        # indirection) rather than using the requireImdsv2 convenience flag.
        instance.instance.add_property_override(
            "MetadataOptions",
            {
                "HttpTokens": "required",
                "HttpPutResponseHopLimit": 2,
                "HttpEndpoint": "enabled",
            },
        )
        Tags.of(instance).add("Name", "iot-hackathon-kafka-connect")

        CfnOutput(self, "KafkaConnectInstanceId", value=instance.instance_id)
        CfnOutput(self, "KafkaConnectPrivateIp", value=instance.instance_private_ip)
