"""An AWS Python Pulumi program"""

import pulumi
from pulumi_aws import s3
import pulumi
import pulumi_aws as aws
from netaddr import IPNetwork
from ephermeral_service import EphemeralService

# Config
config = pulumi.Config()
stack = pulumi.get_stack()

# Network Configuration
VPC_CIDR_BLOCK = "10.0.0.0/16"
vpc_network = IPNetwork(VPC_CIDR_BLOCK)
subnet_prefix = 24
subnets = list(vpc_network.subnet(subnet_prefix))

PRIVATE_SUBNET_1_CIDR_BLOCK = str(subnets[0])
PRIVATE_SUBNET_2_CIDR_BLOCK = str(subnets[1])

# Create VPC
vpc = aws.ec2.Vpc(
    "vpc",
    cidr_block=VPC_CIDR_BLOCK,
    enable_dns_hostnames=True,
    tags={"Name": "migration-test-vpc"}
)

# Create Internet Gateway
internet_gateway = aws.ec2.InternetGateway(
    "internet-gateway",
    vpc_id=vpc.id
)

# Create private subnets
private_subnet_1 = aws.ec2.Subnet(
    "private-subnet-1",
    vpc_id=vpc.id,
    cidr_block=PRIVATE_SUBNET_1_CIDR_BLOCK,
    availability_zone="eu-west-1a",  # Change this to your desired AZ
    tags={"Name": "migration-test-private-1"}
)

private_subnet_2 = aws.ec2.Subnet(
    "private-subnet-2",
    vpc_id=vpc.id,
    cidr_block=PRIVATE_SUBNET_2_CIDR_BLOCK,
    availability_zone="eu-west-1b",  # Change this to your desired AZ
    tags={"Name": "migration-test-private-2"}
)

public_subnet = aws.ec2.Subnet(
    "public-subnet",
    vpc_id=vpc.id,
    cidr_block=str(subnets[2]),  # Using the next available subnet block
    map_public_ip_on_launch=True,
    availability_zone="eu-west-1a",
    tags={"Name": "migration-test-public"}
)

# Create and attach an internet route table to public subnet
public_route_table = aws.ec2.RouteTable(
    "public-route-table",
    vpc_id=vpc.id,
    routes=[{
        "cidr_block": "0.0.0.0/0",
        "gateway_id": internet_gateway.id
    }]
)

aws.ec2.RouteTableAssociation(
    "public-route-table-association",
    subnet_id=public_subnet.id,
    route_table_id=public_route_table.id
)

# Create NAT Gateway (requires an Elastic IP)
eip = aws.ec2.Eip("nat-eip")

nat_gateway = aws.ec2.NatGateway(
    "nat-gateway",
    allocation_id=eip.id,
    subnet_id=public_subnet.id
)

# Update private subnet route table to route through NAT Gateway
private_route_table = aws.ec2.RouteTable(
    "private-route-table",
    vpc_id=vpc.id,
    routes=[{
        "cidr_block": "0.0.0.0/0",
        "nat_gateway_id": nat_gateway.id
    }]
)

# Associate private subnets with the route table
aws.ec2.RouteTableAssociation(
    "private-rt-association-1",
    subnet_id=private_subnet_1.id,
    route_table_id=private_route_table.id
)

aws.ec2.RouteTableAssociation(
    "private-rt-association-2",
    subnet_id=private_subnet_2.id,
    route_table_id=private_route_table.id
)

# Security group for database
db_security_group = aws.ec2.SecurityGroup(
    "db-security-group",
    vpc_id=vpc.id,
    description="Allow database access",
    ingress=[{
        "protocol": "tcp",
        "from_port": 5432,
        "to_port": 5432,
        "cidr_blocks": [VPC_CIDR_BLOCK]
    }],
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"]
    }]
)

# RDS subnet group
rds_subnet_group = aws.rds.SubnetGroup(
    "rds-subnet-group",
    subnet_ids=[private_subnet_1.id, private_subnet_2.id],
)

# Create the database
test_db = aws.rds.Instance(
    "test-db",
    identifier="migration-test-db",
    instance_class="db.t4g.micro",
    allocated_storage=20,
    engine="postgres",
    engine_version="17.1",
    db_name="main",
    username="testuser",  # You'll want to change this
    password="testpassword123",  # You'll want to change this
    skip_final_snapshot=True,  # For test environment
    vpc_security_group_ids=[db_security_group.id],
    db_subnet_group_name=rds_subnet_group.name,
)


# Allow ephemeral service for http connections
ecs_security_group = aws.ec2.SecurityGroup(
    "ecs-security-group",
    vpc_id=vpc.id,
    description="Security group for ECS tasks",
    ingress=[],  # No inbound needed for our test
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"]
    }]
)

migration_service = EphemeralService(
    name="migration-test",
    vpc_id=vpc.id,
    private_subnet_ids=[private_subnet_1.id, private_subnet_2.id],
    security_group_id=ecs_security_group.id,
    environment=[
        "GITHUB_RUNNER_APP_ID", # 1064570
        "GITHUB_RUNNER_PRIVATE_KEY",
        "GITHUB_RUNNER_INSTALLATION_ID",
        "DATABASE_URL"
    ]  # Assuming you'll store the connection string in Parameter Store
)

# Export the run command for easy reference
pulumi.export('run_task_command', migration_service.get_run_task_command())


# Export important values
pulumi.export('vpc_id', vpc.id)
pulumi.export('private_subnet_1_id', private_subnet_1.id)
pulumi.export('private_subnet_2_id', private_subnet_2.id)
pulumi.export('db_endpoint', test_db.endpoint)
pulumi.export('db_username', test_db.username)
pulumi.export('db_name', test_db.db_name)