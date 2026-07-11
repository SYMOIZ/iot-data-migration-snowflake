from pathlib import Path

from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_iot as iot,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct


class IotStack(Stack):
    """IoT Core things/policy + a Lambda that republishes MQTT telemetry onto the
    MSK topic 'iot-events' (IoT Core Rule -> Lambda -> Kafka, IAM-authenticated)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        sg_msk_client: ec2.SecurityGroup,
        msk_cluster_arn: str,
        msk_bootstrap_servers: str,
        project_name_for_topic: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name")
        topic = self.node.try_get_context("kafka_topic")
        device_count = self.node.try_get_context("device_count")

        # --- IoT Thing registry for the simulated devices. The simulator (iot-simulator/)
        # authenticates over MQTT-over-WebSocket with SigV4 (the deployer's IAM
        # credentials), not X.509 certs, so no per-thing certificate/policy
        # attachment is needed here - just the Thing registry entries themselves.
        self.things = []
        for i in range(1, device_count + 1):
            thing_name = f"{project}-device-{i:03d}"
            thing = iot.CfnThing(self, f"Device{i}", thing_name=thing_name)
            self.things.append(thing)

        # --- Lambda: IoT Rule target, republishes onto MSK ---
        layer = _lambda.LayerVersion(
            self,
            "KafkaProducerLayer",
            code=_lambda.Code.from_asset(str(Path(__file__).resolve().parents[2] / "lambda" / "layer")),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="kafka-python (native AWS_MSK_IAM sasl mechanism)",
        )

        fn_role = iam.Role(
            self,
            "IotToKafkaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )
        fn_role.add_to_policy(
            iam.PolicyStatement(
                actions=["kafka-cluster:Connect"],
                resources=[msk_cluster_arn],
            )
        )
        fn_role.add_to_policy(
            iam.PolicyStatement(
                actions=["kafka-cluster:WriteData", "kafka-cluster:DescribeTopic"],
                resources=[
                    f"arn:aws:kafka:{self.region}:{self.account}:topic/{project_name_for_topic}/*"
                ],
            )
        )

        log_group = logs.LogGroup(
            self,
            "IotToKafkaLogGroup",
            log_group_name=f"/aws/lambda/{project}-iot-to-kafka",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.iot_to_kafka_fn = _lambda.Function(
            self,
            "IotToKafkaFn",
            function_name=f"{project}-iot-to-kafka",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset(str(Path(__file__).resolve().parents[2] / "lambda" / "iot_to_kafka")),
            layers=[layer],
            role=fn_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[sg_msk_client],
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "MSK_BOOTSTRAP_SERVERS": msk_bootstrap_servers,
                "KAFKA_TOPIC": topic,
            },
            log_group=log_group,
        )

        # --- IoT Topic Rule: iot/<device>/telemetry -> Lambda ---
        self.iot_to_kafka_fn.add_permission(
            "IotInvoke",
            principal=iam.ServicePrincipal("iot.amazonaws.com"),
            source_arn=f"arn:aws:iot:{self.region}:{self.account}:rule/{project.replace('-', '_')}_to_kafka",
        )

        iot.CfnTopicRule(
            self,
            "IotToKafkaRule",
            rule_name=f"{project.replace('-', '_')}_to_kafka",
            topic_rule_payload=iot.CfnTopicRule.TopicRulePayloadProperty(
                sql="SELECT * FROM 'iot/+/telemetry'",
                aws_iot_sql_version="2016-03-23",
                actions=[
                    iot.CfnTopicRule.ActionProperty(
                        lambda_=iot.CfnTopicRule.LambdaActionProperty(
                            function_arn=self.iot_to_kafka_fn.function_arn
                        )
                    )
                ],
                error_action=iot.CfnTopicRule.ActionProperty(
                    cloudwatch_logs=iot.CfnTopicRule.CloudwatchLogsActionProperty(
                        log_group_name=log_group.log_group_name,
                        role_arn=iam.Role(
                            self,
                            "IotErrorLoggingRole",
                            assumed_by=iam.ServicePrincipal("iot.amazonaws.com"),
                            inline_policies={
                                "WriteLogs": iam.PolicyDocument(
                                    statements=[
                                        iam.PolicyStatement(
                                            actions=["logs:PutLogEvents", "logs:CreateLogStream"],
                                            resources=[log_group.log_group_arn + ":*"],
                                        )
                                    ]
                                )
                            },
                        ).role_arn,
                    )
                ),
            ),
        )

        cloudwatch.Alarm(
            self,
            "IotToKafkaErrorsAlarm",
            metric=self.iot_to_kafka_fn.metric_errors(period=Duration.minutes(5)),
            threshold=5,
            evaluation_periods=1,
            alarm_description="IoT->Kafka Lambda errored 5+ times in 5 minutes",
        )

        CfnOutput(self, "IotToKafkaFunctionName", value=self.iot_to_kafka_fn.function_name)
        CfnOutput(self, "IotEndpoint", value=f"iot.{self.region}.amazonaws.com (use `aws iot describe-endpoint`)")
        CfnOutput(self, "DeviceThingNames", value=",".join(t.thing_name for t in self.things))
