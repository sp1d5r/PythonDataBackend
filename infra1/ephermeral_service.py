import json
import pulumi
import pulumi_aws as aws
import boto3

class EphemeralService:
    """Simplified ephemeral service for testing migrations"""

    def __init__(
            self,
            name: str,
            vpc_id: str,
            private_subnet_ids: list,
            security_group_id: str,
            memory: float = 0.5,  # GiB
            cpu: float = 0.25,    # vCPU
            environment: list = [],
        ):
        self.name = name
        self.memory = memory
        self.cpu = cpu
        self.environment = environment
        self.vpc_id = vpc_id
        self.private_subnet_ids = private_subnet_ids
        self.security_group_id = security_group_id

        # Create ECR repository for our migration images
        self.ecr_repository = aws.ecr.Repository(
            f"{name}-ecr-repository",
            name=f"{name}",
            force_delete=True,  # Allow deletion for testing
        )

        self.log_group = aws.cloudwatch.LogGroup(
            f"{name}-logs",
            name=f"/ecs/{name}",
            retention_in_days=7,
        )

        # Create ECS Cluster
        self.cluster = aws.ecs.Cluster(
            f"{self.name}-cluster",
            name=f"{self.name}-cluster"
        )

        # Set up task execution role
        self.execution_role = self.create_execution_role()
        self.task_role = self.create_task_role()

        # Create Task Definition
        self.setup_task_definition()

    def create_execution_role(self):
        """Create the execution role for Fargate tasks"""
        role = aws.iam.Role(
            f"{self.name}-execution-role",
            assume_role_policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Action": "sts:AssumeRole",
                    "Principal": {
                        "Service": "ecs-tasks.amazonaws.com"
                    },
                    "Effect": "Allow"
                }]
            })
        )

        aws.iam.RolePolicyAttachment(
            f"{self.name}-execution-policy",
            role=role.name,
            policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
        )

        return role

    def create_task_role(self):
        """Create the task role with permissions to access secrets/parameters"""
        role = aws.iam.Role(
            f"{self.name}-task-role",
            assume_role_policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Action": "sts:AssumeRole",
                    "Principal": {
                        "Service": "ecs-tasks.amazonaws.com"
                    },
                    "Effect": "Allow"
                }]
            })
        )

        aws.iam.RolePolicy(
            f"{self.name}-task-policy",
            role=role.name,
            policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "ssm:GetParameter*"
                    ],
                    "Resource": "*"
                }]
            })
        )

        return role

    def get_latest_version_tag(self):
        """Get latest version tag (will be github sha) from ECR"""
        client = boto3.client('ecr')
        try:
            response = client.describe_images(
                repositoryName=self.name,
                filter={'tagStatus': 'TAGGED'}
            )
            if not response.get('imageDetails'):
                return 'latest'  # Default if no images found

            # Sort by pushed date and get the most recent
            sorted_images = sorted(
                response['imageDetails'],
                key=lambda x: x['imagePushedAt'],
                reverse=True
            )

            # Look for version tags
            for image in sorted_images:
                for tag in image.get('imageTags', []):
                    if tag.startswith('v'):
                        return tag
            return 'latest'  # Fallback if no version tags found
        except Exception as e:
            print(f"Error getting latest version tag: {e}")
            return 'latest'

    def setup_task_definition(self):
        """Setup the Fargate task definition"""
        environment = [
            {
                "name": param,
                "value": aws.ssm.get_parameter(name=param).value
            } for param in self.environment
        ]

        # Get the latest version tag
        version_tag = self.get_latest_version_tag()

        self.task_definition = aws.ecs.TaskDefinition(
            f"{self.name}-task",
            family=f"{self.name}-task-family",
            cpu=str(int(self.cpu * 1024)),
            memory=str(int(self.memory * 1024)),
            network_mode="awsvpc",
            requires_compatibilities=["FARGATE"],
            execution_role_arn=self.execution_role.arn,
            task_role_arn=self.task_role.arn,
            container_definitions=pulumi.Output.all(
                repository_url=self.ecr_repository.repository_url,
                version=version_tag
            ).apply(
                lambda args: json.dumps([{
                    "name": self.name,
                    "image": f"{args['repository_url']}:{args['version']}",
                    "essential": True,
                    "environment": environment,
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": f"/ecs/{self.name}",
                            "awslogs-region": pulumi.Config("aws").require("region"),
                            "awslogs-stream-prefix": "ecs"
                        }
                    }
                }])
            )
        )

    @property
    def network_config(self):
        """Returns the network configuration for running tasks"""
        return {
            "awsvpcConfiguration": {
                "subnets": self.private_subnet_ids,
                "securityGroups": [self.security_group_id],
                "assignPublicIp": "DISABLED"
            }
        }

    def get_run_task_command(self):
        """Returns the AWS CLI command to run this task"""
        return pulumi.Output.all(
            subnets=self.private_subnet_ids,
            security_group=self.security_group_id
        ).apply(lambda args: f"""aws ecs run-task \\
        --cluster {self.name}-cluster \\
        --task-definition {self.name}-task-family:latest \\
        --launch-type FARGATE \\
        --network-configuration '{{"awsvpcConfiguration": {{"subnets": {args["subnets"]}, "securityGroups": ["{args["security_group"]}"], "assignPublicIp": "DISABLED"}}}}'""")
