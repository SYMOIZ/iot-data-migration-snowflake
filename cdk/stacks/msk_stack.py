import base64

from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
    aws_msk as msk,
    aws_kafkaconnect as kafkaconnect,
    aws_cloudwatch as cloudwatch,
    custom_resources as cr,
)
from constructs import Construct


class MskStack(Stack):
    """MSK provisioned cluster (IAM auth) + MSK Connect custom plugins/worker config +
    the JDBC sink connector (iot-events -> PostgreSQL). The Debezium Postgres source
    connector (Phase 2 CDC) plugin is uploaded here too, but the connector itself is
    created later (scripts/deploy-debezium-connector.sh) once WAL/publication is confirmed.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        sg_msk: ec2.SecurityGroup,
        sg_msk_client: ec2.SecurityGroup,
        plugins_bucket,
        jdbc_plugin_deployment,
        debezium_plugin_deployment,
        db_secret,
        postgres_instance,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name")
        instance_type = self.node.try_get_context("msk_instance_type")
        broker_count = self.node.try_get_context("msk_broker_count")
        ebs_gb = self.node.try_get_context("msk_ebs_gb")
        kafka_version = self.node.try_get_context("msk_kafka_version")
        db_name = self.node.try_get_context("db_name")
        topic = self.node.try_get_context("kafka_topic")

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
                sasl=msk.CfnCluster.SaslProperty(
                    iam=msk.CfnCluster.IamProperty(enabled=True)
                )
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
        # (the JDBC sink connector below, and the IoT->Kafka Lambda in IotStack).
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

        # --- MSK Connect: custom plugins built from cdk/assets/plugins/*/plugin.zip ---
        self.jdbc_plugin = kafkaconnect.CfnCustomPlugin(
            self,
            "JdbcSinkPlugin",
            name=f"{project}-debezium-jdbc-sink",
            content_type="ZIP",
            location=kafkaconnect.CfnCustomPlugin.CustomPluginLocationProperty(
                s3_location=kafkaconnect.CfnCustomPlugin.S3LocationProperty(
                    bucket_arn=plugins_bucket.bucket_arn,
                    file_key="jdbc-sink/plugin.zip",
                )
            ),
        )
        self.jdbc_plugin.node.add_dependency(jdbc_plugin_deployment)

        self.debezium_plugin = kafkaconnect.CfnCustomPlugin(
            self,
            "DebeziumPostgresPlugin",
            name=f"{project}-debezium-postgres-source",
            content_type="ZIP",
            location=kafkaconnect.CfnCustomPlugin.CustomPluginLocationProperty(
                s3_location=kafkaconnect.CfnCustomPlugin.S3LocationProperty(
                    bucket_arn=plugins_bucket.bucket_arn,
                    file_key="debezium-postgres/plugin.zip",
                )
            ),
        )
        self.debezium_plugin.node.add_dependency(debezium_plugin_deployment)

        connect_log_group = logs.LogGroup(
            self,
            "MskConnectLogGroup",
            log_group_name=f"/iot-hackathon/msk-connect/{project}",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        worker_props = (
            "key.converter=org.apache.kafka.connect.json.JsonConverter\n"
            "value.converter=org.apache.kafka.connect.json.JsonConverter\n"
            "key.converter.schemas.enable=false\n"
            "value.converter.schemas.enable=false\n"
        )
        self.worker_config = kafkaconnect.CfnWorkerConfiguration(
            self,
            "ConnectWorkerConfig",
            name=f"{project}-json-worker-config",
            properties_file_content=base64.b64encode(worker_props.encode()).decode(),
        )

        # --- Service execution role for MSK Connect (scoped, no wildcard resources where avoidable) ---
        connect_role = iam.Role(
            self,
            "MskConnectRole",
            assumed_by=iam.ServicePrincipal("kafkaconnect.amazonaws.com"),
        )
        connect_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kafka-cluster:Connect",
                    "kafka-cluster:AlterCluster",
                    "kafka-cluster:DescribeCluster",
                ],
                resources=[self.cluster.attr_arn],
            )
        )
        connect_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kafka-cluster:*Topic*",
                    "kafka-cluster:ReadData",
                    "kafka-cluster:WriteData",
                ],
                resources=[
                    f"arn:aws:kafka:{self.region}:{self.account}:topic/{project}-msk/*"
                ],
            )
        )
        connect_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kafka-cluster:AlterGroup",
                    "kafka-cluster:DescribeGroup",
                ],
                resources=[
                    f"arn:aws:kafka:{self.region}:{self.account}:group/{project}-msk/*"
                ],
            )
        )
        plugins_bucket.grant_read(connect_role)
        db_secret.grant_read(connect_role)
        connect_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogStream",
                    "logs:CreateLogGroup",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        pg_endpoint = postgres_instance.instance_private_ip

        jdbc_sink_config = {
            "connector.class": "io.debezium.connector.jdbc.JdbcSinkConnector",
            "tasks.max": "1",
            "topics": topic,
            "connection.url": f"jdbc:postgresql://{pg_endpoint}:5432/{db_name}",
            "connection.username": f"${{secretManager:{db_secret.secret_arn}:username}}",
            "connection.password": f"${{secretManager:{db_secret.secret_arn}:password}}",
            "insert.mode": "upsert",
            "primary.key.mode": "record_value",
            "primary.key.fields": "device_id,event_time",
            "table.name.format": "device_telemetry",
            "schema.evolution": "basic",
            "delete.enabled": "false",
            "database.time_zone": "UTC",
        }

        self.jdbc_sink_connector = kafkaconnect.CfnConnector(
            self,
            "JdbcSinkConnector",
            connector_name=f"{project}-jdbc-sink",
            kafka_cluster=kafkaconnect.CfnConnector.KafkaClusterProperty(
                apache_kafka_cluster=kafkaconnect.CfnConnector.ApacheKafkaClusterProperty(
                    bootstrap_servers=self.bootstrap_brokers_sasl_iam,
                    vpc=kafkaconnect.CfnConnector.VpcProperty(
                        subnets=private_subnet_ids,
                        security_groups=[sg_msk_client.security_group_id],
                    ),
                )
            ),
            kafka_cluster_client_authentication=kafkaconnect.CfnConnector.KafkaClusterClientAuthenticationProperty(
                authentication_type="IAM"
            ),
            kafka_cluster_encryption_in_transit=kafkaconnect.CfnConnector.KafkaClusterEncryptionInTransitProperty(
                encryption_type="TLS"
            ),
            capacity=kafkaconnect.CfnConnector.CapacityProperty(
                provisioned_capacity=kafkaconnect.CfnConnector.ProvisionedCapacityProperty(
                    mcu_count=1, worker_count=1
                )
            ),
            connector_configuration=jdbc_sink_config,
            kafka_connect_version="2.7.1",
            plugins=[
                kafkaconnect.CfnConnector.PluginProperty(
                    custom_plugin=kafkaconnect.CfnConnector.CustomPluginProperty(
                        custom_plugin_arn=self.jdbc_plugin.attr_custom_plugin_arn,
                        revision=self.jdbc_plugin.attr_revision,
                    )
                )
            ],
            service_execution_role_arn=connect_role.role_arn,
            worker_configuration=kafkaconnect.CfnConnector.WorkerConfigurationProperty(
                worker_configuration_arn=self.worker_config.attr_worker_configuration_arn,
                revision=self.worker_config.attr_revision,
            ),
            log_delivery=kafkaconnect.CfnConnector.LogDeliveryProperty(
                worker_log_delivery=kafkaconnect.CfnConnector.WorkerLogDeliveryProperty(
                    cloud_watch_logs=kafkaconnect.CfnConnector.CloudWatchLogsLogDeliveryProperty(
                        enabled=True, log_group=connect_log_group.log_group_name
                    )
                )
            ),
        )
        self.jdbc_sink_connector.node.add_dependency(self.cluster)
        self.jdbc_sink_connector.node.add_dependency(postgres_instance)

        # --- CloudWatch alarms ---
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

        self.jdbc_plugin_ref = self.jdbc_plugin
        CfnOutput(self, "MskClusterArn", value=self.cluster.attr_arn)
        CfnOutput(
            self, "MskBootstrapBrokersIam", value=self.bootstrap_brokers_sasl_iam
        )
