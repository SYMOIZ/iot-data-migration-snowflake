from aws_cdk import (
    Stack,
    Tags,
    CfnOutput,
    RemovalPolicy,
    aws_msk as msk,
    aws_logs as logs,
)
from constructs import Construct

# Existing resources from the already-deployed IotHackathon-Network stack.
# This stack IMPORTS them only - it never creates or manages VPC, subnet,
# or security group resources.
PRIVATE_SUBNET_AZ1 = "subnet-0b48a9b72ff904555"
PRIVATE_SUBNET_AZ2 = "subnet-0f7951f481e8144a5"
MSK_SG_ID = "sg-02b40d867975ba242"

CLUSTER_NAME = "iot-hackathon-msk"


class MskStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        Tags.of(self).add("project", "iot-hackathon")
        Tags.of(self).add("phase", "1")
        Tags.of(self).add("task", "1.3")
        Tags.of(self).add("managed-by", "cdk")

        log_group = logs.LogGroup(
            self,
            "MskBrokerLogGroup",
            log_group_name="/aws/msk/iot-hackathon",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        cluster = msk.CfnCluster(
            self,
            "MskCluster",
            cluster_name=CLUSTER_NAME,
            kafka_version="3.9.x",
            number_of_broker_nodes=2,
            broker_node_group_info=msk.CfnCluster.BrokerNodeGroupInfoProperty(
                instance_type="kafka.t3.small",
                client_subnets=[PRIVATE_SUBNET_AZ1, PRIVATE_SUBNET_AZ2],
                security_groups=[MSK_SG_ID],
                storage_info=msk.CfnCluster.StorageInfoProperty(
                    ebs_storage_info=msk.CfnCluster.EBSStorageInfoProperty(
                        volume_size=20
                    )
                ),
            ),
            encryption_info=msk.CfnCluster.EncryptionInfoProperty(
                encryption_in_transit=msk.CfnCluster.EncryptionInTransitProperty(
                    client_broker="TLS",
                    in_cluster=True,
                )
            ),
            client_authentication=msk.CfnCluster.ClientAuthenticationProperty(
                sasl=msk.CfnCluster.SaslProperty(
                    iam=msk.CfnCluster.IamProperty(enabled=True)
                ),
                unauthenticated=msk.CfnCluster.UnauthenticatedProperty(enabled=False),
            ),
            enhanced_monitoring="DEFAULT",
            logging_info=msk.CfnCluster.LoggingInfoProperty(
                broker_logs=msk.CfnCluster.BrokerLogsProperty(
                    cloud_watch_logs=msk.CfnCluster.CloudWatchLogsProperty(
                        enabled=True, log_group=log_group.log_group_name
                    )
                )
            ),
            tags={
                "project": "iot-hackathon",
                "phase": "1",
                "task": "1.3",
                "managed-by": "cdk",
                "Name": CLUSTER_NAME,
            },
        )

        CfnOutput(self, "ClusterArn", value=cluster.ref)
        CfnOutput(self, "ClusterName", value=CLUSTER_NAME)
