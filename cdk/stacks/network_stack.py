from aws_cdk import Stack, CfnOutput, aws_ec2 as ec2
from constructs import Construct


class NetworkStack(Stack):
    """VPC + subnets + route tables + security groups for the IoT hackathon pipeline.

    One NAT gateway is provisioned (not per-AZ) because the private-subnet workloads
    (Postgres EC2, MSK Connect ENIs, Lambda) need outbound internet for package
    installs / SSM / plugin downloads, but do not need multi-AZ NAT resilience for
    a hackathon workload. An S3 gateway endpoint (no hourly cost) offloads S3
    traffic (backups, connector plugins) from the NAT gateway.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name")
        cidr = self.node.try_get_context("vpc_cidr")
        max_azs = self.node.try_get_context("max_azs")
        nat_gateways = self.node.try_get_context("nat_gateways")

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            vpc_name=f"{project}-vpc",
            ip_addresses=ec2.IpAddresses.cidr(cidr),
            max_azs=max_azs,
            nat_gateways=nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # Free gateway endpoint so S3 traffic (backups, Connect plugins) skips the NAT gateway.
        self.vpc.add_gateway_endpoint(
            "S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3
        )
        # Interface endpoints so SSM Session Manager works even if NAT/egress is later tightened.
        for name, service in [
            ("Ssm", ec2.InterfaceVpcEndpointAwsService.SSM),
            ("SsmMessages", ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES),
            ("Ec2Messages", ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES),
            ("SecretsManager", ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER),
        ]:
            self.vpc.add_interface_endpoint(
                f"{name}Endpoint", service=service, private_dns_enabled=True
            )

        # --- Security groups ---
        self.sg_bastion = ec2.SecurityGroup(
            self,
            "BastionSg",
            vpc=self.vpc,
            description="Bastion host - no inbound, SSM Session Manager only",
            allow_all_outbound=True,
            security_group_name=f"{project}-bastion-sg",
        )

        self.sg_msk_client = ec2.SecurityGroup(
            self,
            "MskClientSg",
            vpc=self.vpc,
            description="Attached to anything that talks to MSK as a client: MSK Connect, Lambda producer, bastion admin",
            allow_all_outbound=True,
            security_group_name=f"{project}-msk-client-sg",
        )

        self.sg_msk = ec2.SecurityGroup(
            self,
            "MskSg",
            vpc=self.vpc,
            description="MSK broker security group",
            allow_all_outbound=True,
            security_group_name=f"{project}-msk-sg",
        )
        for port in (9098, 9094, 9092):
            self.sg_msk.add_ingress_rule(
                self.sg_msk_client, ec2.Port.tcp(port), f"Kafka client access on {port}"
            )
        self.sg_msk.add_ingress_rule(
            self.sg_bastion, ec2.Port.tcp_range(9092, 9098), "Bastion admin access to brokers"
        )

        self.sg_postgres = ec2.SecurityGroup(
            self,
            "PostgresSg",
            vpc=self.vpc,
            description="PostgreSQL EC2 (on-prem simulation) security group",
            allow_all_outbound=True,
            security_group_name=f"{project}-postgres-sg",
        )
        self.sg_postgres.add_ingress_rule(
            self.sg_msk_client, ec2.Port.tcp(5432), "Kafka Connect JDBC sink access"
        )
        self.sg_postgres.add_ingress_rule(
            self.sg_bastion, ec2.Port.tcp(5432), "Bastion admin access to Postgres"
        )

        CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
        CfnOutput(
            self,
            "PrivateSubnetIds",
            value=",".join(s.subnet_id for s in self.vpc.private_subnets),
        )
        CfnOutput(
            self,
            "PublicSubnetIds",
            value=",".join(s.subnet_id for s in self.vpc.public_subnets),
        )
