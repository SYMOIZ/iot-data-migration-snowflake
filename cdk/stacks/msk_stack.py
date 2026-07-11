from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_logs as logs,
    aws_msk as msk,
    aws_cloudwatch as cloudwatch,
    custom_resources as cr,
)
from constructs import Construct


class MskStack(Stack):
    """MSK provisioned cluster (IAM auth) only. Kafka Connect runs separately on a
    self-managed EC2 host (see kafka_connect_stack.py) rather than MSK Connect.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        sg_msk: ec2.SecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name")
        instance_type = self.node.try_get_context("msk_instance_type")
        broker_count = self.node.try_get_context("msk_broker_count")
        ebs_gb = self.node.try_get_context("msk_ebs_gb")
        kafka_version = self.node.try_get_context("msk_kafka_version")

        broker_log_group = logs.LogGroup(
            self,
            "MskBrokerLogGroup",
            log_group_name=f"/iot-hackathon/msk/{project}-brokers",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        private_subnet_ids = [s.subnet_id for s in vpc.private_subnets]

        self.cluster = msk.CfnCluster(
            self,
            "MskCluster",
            cluster_name=f"{project}-msk",
            kafka_version=kafka_version,
            number_of_broker_nodes=broker_count,
            broker_node_group_info=msk.CfnCluster.BrokerNodeGroupInfoProperty(
                instance_type=instance_type,
                client_subnets=private_subnet_ids,
                security_groups=[sg_msk.security_group_id],
                storage_info=msk.CfnCluster.StorageInfoProperty(
                    ebs_storage_info=msk.CfnCluster.EBSStorageInfoProperty(volume_size=ebs_gb)
                ),
            ),
            encryption_info=msk.CfnCluster.EncryptionInfoProperty(
                encryption_in_transit=msk.CfnCluster.EncryptionInTransitProperty(
                    client_broker="TLS", in_cluster=True
                )
            ),
            client_authentication=msk.CfnCluster.ClientAuthenticationProperty(
                sasl=msk.CfnCluster.SaslProperty(iam=msk.CfnCluster.IamProperty(enabled=True))
            ),
            logging_info=msk.CfnCluster.LoggingInfoProperty(
                broker_logs=msk.CfnCluster.BrokerLogsProperty(
                    cloud_watch_logs=msk.CfnCluster.CloudWatchLogsProperty(
                        enabled=True, log_group=broker_log_group.log_group_name
                    )
                )
            ),
            enhanced_monitoring="PER_TOPIC_PER_BROKER",
        )

        # Bootstrap broker strings are NOT exposed via CloudFormation Fn::GetAtt on
        # AWS::MSK::Cluster - they only exist via the kafka:GetBootstrapBrokers API,
        # so a Custom Resource fetches them post-creation for downstream consumers
        # (the Kafka Connect EC2 host, and the IoT->Kafka Lambda in IotStack).
        bootstrap_brokers_cr = cr.AwsCustomResource(
            self,
            "GetBootstrapBrokers",
            on_create=cr.AwsSdkCall(
                service="Kafka",
                action="getBootstrapBrokers",
                parameters={"ClusterArn": self.cluster.attr_arn},
                physical_resource_id=cr.PhysicalResourceId.of(f"{project}-bootstrap-brokers"),
            ),
            on_update=cr.AwsSdkCall(
                service="Kafka",
                action="getBootstrapBrokers",
                parameters={"ClusterArn": self.cluster.attr_arn},
                physical_resource_id=cr.PhysicalResourceId.of(f"{project}-bootstrap-brokers"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
            ),
            install_latest_aws_sdk=False,
        )
        bootstrap_brokers_cr.node.add_dependency(self.cluster)
        self.bootstrap_brokers_sasl_iam = bootstrap_brokers_cr.get_response_field(
            "BootstrapBrokerStringSaslIam"
        )

        cloudwatch.Alarm(
            self,
            "MskBrokerCpuAlarm",
            metric=cloudwatch.Metric(
                namespace="AWS/Kafka",
                metric_name="CpuUser",
                dimensions_map={"Cluster Name": f"{project}-msk"},
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=80,
            evaluation_periods=3,
            alarm_description="MSK broker CPU > 80% for 15 minutes",
        )

        CfnOutput(self, "MskClusterArn", value=self.cluster.attr_arn)
        CfnOutput(self, "MskBootstrapBrokersIam", value=self.bootstrap_brokers_sasl_iam)
