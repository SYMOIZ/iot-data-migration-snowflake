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

# Fixed KRaft cluster ID (base64, 22 chars) - generated once, kept stable so
# re-running UserData / restarting the container doesn't regenerate storage.
KRAFT_CLUSTER_ID = "MkU3OEVBNTcwNTJENDM2Qk"

KAFKA_USER_DATA = f"""#!/bin/bash
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

TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
PRIVATE_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4)

mkdir -p /opt/kafka
cd /opt/kafka

cat > docker-compose.yml << EOCOMPOSE
services:
  kafka:
    image: bitnami/kafka:3.8
    container_name: kafka
    restart: unless-stopped
    network_mode: host
    environment:
      KAFKA_ENABLE_KRAFT: "yes"
      KAFKA_CFG_PROCESS_ROLES: "broker,controller"
      KAFKA_CFG_NODE_ID: "1"
      KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: "1@127.0.0.1:9093"
      KAFKA_CFG_LISTENERS: "PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093"
      KAFKA_CFG_ADVERTISED_LISTENERS: "PLAINTEXT://${{PRIVATE_IP}}:9092"
      KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP: "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT"
      KAFKA_CFG_CONTROLLER_LISTENER_NAMES: "CONTROLLER"
      ALLOW_PLAINTEXT_LISTENER: "yes"
      KAFKA_KRAFT_CLUSTER_ID: "{KRAFT_CLUSTER_ID}"
      KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE: "false"
      KAFKA_CFG_OFFSETS_TOPIC_REPLICATION_FACTOR: "1"
      KAFKA_CFG_DEFAULT_REPLICATION_FACTOR: "1"
      KAFKA_CFG_NUM_PARTITIONS: "3"
    volumes:
      - kafka-data:/bitnami/kafka
volumes:
  kafka-data:
EOCOMPOSE

docker compose -f docker-compose.yml up -d

# Wait for the broker to accept connections before creating topics
for i in $(seq 1 30); do
  if docker exec kafka /opt/bitnami/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092 > /dev/null 2>&1; then
    break
  fi
  sleep 5
done

docker exec kafka /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \\
  --create --if-not-exists --topic iot-events --partitions 3 --replication-factor 1
docker exec kafka /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \\
  --create --if-not-exists --topic cdc.public.iot_events --partitions 3 --replication-factor 1

touch /var/log/kafka-bootstrap-complete
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
            user_data=ec2.UserData.custom(KAFKA_USER_DATA),
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
