from aws_cdk import (
    Stack,
    Tags,
    CfnOutput,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

# Existing resources from the already-deployed IotHackathon-Network / IotHackathon-Security
# stacks. This stack IMPORTS them only - it never creates or manages VPC, subnet, IAM,
# Secrets Manager, or S3 resources.
VPC_ID = "vpc-06802348bb7d24fd8"
AZ_1 = "us-east-1a"
AZ_2 = "us-east-1b"
PRIVATE_SUBNET_AZ1 = "subnet-0b48a9b72ff904555"
PRIVATE_SUBNET_AZ2 = "subnet-0f7951f481e8144a5"
POSTGRES_SG_ID = "sg-06fe414b9af87ff6a"
BASTION_SG_ID = "sg-080bebdbe86f2aea2"
DB_SECRET_ARN = (
    "arn:aws:secretsmanager:us-east-1:159412676011:"
    "secret:iot-hackathon/postgres/credentials-ZYGBYl"
)
VPC_CIDR = "10.42.0.0/16"

POSTGRES_USER_DATA = f"""#!/bin/bash
set -eux
exec > /var/log/user-data.log 2>&1

dnf update -y
dnf install -y postgresql16 postgresql16-server unzip xfsprogs

# AWS CLI v2 (needed to read the DB credentials secret at boot).
# Amazon Linux 2023 ships curl-minimal by default, which conflicts with the
# full "curl" package - use the pre-installed curl-minimal binary instead of
# installing "curl" separately. Idempotent: skips if already installed.
if ! command -v /usr/local/bin/aws > /dev/null 2>&1; then
  curl -s -o /tmp/awscliv2.zip "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"
  cd /tmp && unzip -q -o awscliv2.zip && ./aws/install
fi

# Locate the dedicated data EBS volume (root is always nvme0n1 on Nitro instances)
# and mount it under /var/lib/pgsql before initdb so PGDATA lives on it. Idempotent:
# only formats if the device has no filesystem yet, only mounts if not already mounted.
DATA_DEV=$(lsblk -dn -o NAME | grep '^nvme' | grep -v '^nvme0n1$' | head -n1)
if ! blkid "/dev/${{DATA_DEV}}" > /dev/null 2>&1; then
  mkfs -t xfs "/dev/${{DATA_DEV}}"
fi
mkdir -p /var/lib/pgsql
grep -q "${{DATA_DEV}}" /etc/fstab || echo "/dev/${{DATA_DEV}} /var/lib/pgsql xfs defaults,nofail 0 2" >> /etc/fstab
mountpoint -q /var/lib/pgsql || mount -a
chown postgres:postgres /var/lib/pgsql

if [ ! -f /var/lib/pgsql/data/PG_VERSION ]; then
  postgresql-setup --initdb
fi

PGCONF=/var/lib/pgsql/data/postgresql.conf
PGHBA=/var/lib/pgsql/data/pg_hba.conf

sed -i "s/^#listen_addresses.*/listen_addresses = '*'/" "$PGCONF"
grep -q "^wal_level" "$PGCONF" || cat >> "$PGCONF" <<EOC
wal_level = logical
max_wal_senders = 10
max_replication_slots = 10
EOC

grep -q "{VPC_CIDR}" "$PGHBA" || cat >> "$PGHBA" <<EOC
host all all {VPC_CIDR} scram-sha-256
host replication all {VPC_CIDR} scram-sha-256
EOC

systemctl enable postgresql
systemctl restart postgresql
sleep 3

# Pull DB credentials from Secrets Manager using the instance role - never hardcoded.
# Tracing is disabled around this block so the password is never written to
# /var/log/user-data.log (set -x would otherwise echo expanded command arguments).
set +x
SECRET_JSON=$(/usr/local/bin/aws secretsmanager get-secret-value \\
  --secret-id "{DB_SECRET_ARN}" --region us-east-1 --query SecretString --output text)
DB_NAME=$(echo "$SECRET_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['dbname'])")
DB_USER=$(echo "$SECRET_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['username'])")
DB_PASS=$(echo "$SECRET_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['password'])")

# Idempotent: only creates the role/database if they don't already exist. Uses
# psql's top-level :'var' substitution (not valid inside DO $$ ... $$ bodies).
sudo -u postgres psql -v ON_ERROR_STOP=1 -v dbuser="$DB_USER" -v dbpass="$DB_PASS" -v dbname="$DB_NAME" <<'EOSQL'
SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L REPLICATION', :'dbuser', :'dbpass')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'dbuser')\\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'dbname', :'dbuser')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'dbname')\\gexec
GRANT ALL PRIVILEGES ON DATABASE :"dbname" TO :"dbuser";
EOSQL

unset SECRET_JSON DB_PASS
set -x

touch /var/log/postgres-bootstrap-complete
"""

BASTION_USER_DATA = """#!/bin/bash
set -eux
exec > /var/log/user-data.log 2>&1
dnf update -y
dnf install -y postgresql16
touch /var/log/bastion-bootstrap-complete
"""


class DatabaseStack(Stack):
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
            private_subnet_ids=[PRIVATE_SUBNET_AZ1, PRIVATE_SUBNET_AZ2],
        )

        postgres_sg = ec2.SecurityGroup.from_security_group_id(
            self, "ImportedPostgresSg", POSTGRES_SG_ID, mutable=False
        )
        bastion_sg = ec2.SecurityGroup.from_security_group_id(
            self, "ImportedBastionSg", BASTION_SG_ID, mutable=False
        )
        db_secret = secretsmanager.Secret.from_secret_complete_arn(
            self, "ImportedDbSecret", DB_SECRET_ARN
        )

        postgres_role = iam.Role(
            self,
            "PostgresInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )
        db_secret.grant_read(postgres_role)

        bastion_role = iam.Role(
            self,
            "BastionInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        postgres_instance = ec2.Instance(
            self,
            "PostgresInstance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.LARGE
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[vpc.private_subnets[0]]),
            security_group=postgres_sg,
            role=postgres_role,
            require_imdsv2=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/sdf",
                    volume=ec2.BlockDeviceVolume.ebs(
                        30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
            user_data=ec2.UserData.custom(POSTGRES_USER_DATA),
        )
        Tags.of(postgres_instance).add("Name", "iot-hackathon-postgres-onprem")

        bastion_instance = ec2.Instance(
            self,
            "BastionInstance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[vpc.private_subnets[0]]),
            security_group=bastion_sg,
            role=bastion_role,
            require_imdsv2=True,
            user_data=ec2.UserData.custom(BASTION_USER_DATA),
        )
        Tags.of(bastion_instance).add("Name", "iot-hackathon-bastion")

        CfnOutput(self, "PostgresInstanceId", value=postgres_instance.instance_id)
        CfnOutput(
            self,
            "PostgresPrivateIp",
            value=postgres_instance.instance_private_ip,
        )
        CfnOutput(self, "BastionInstanceId", value=bastion_instance.instance_id)
        CfnOutput(
            self, "BastionPrivateIp", value=bastion_instance.instance_private_ip
        )
        CfnOutput(self, "DbSecretArnUsed", value=DB_SECRET_ARN)
