import sys
import os
import errno
import boto3
import botocore
import json
import datetime
import logging

from git import Repo

logging.basicConfig(format="%(asctime)s - %(levelname)s: %(message)s")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

OPERATIONS = [
    "create",
    "update",
    "delete",
    "create_change_set",
    "delete_change_set",
    "execute_change_set",
]

client = boto3.client("cloudformation")

# TODO: Next session
# 1. Find a way to manage the exceptions and its propagation
# 2. Integrate SOPS
# 4. Find a better way to call the operations
# 8. Improve the way that waiter is called.
# 9. Improve the name of the read_file function


class Stack:
    def __init__(self, stack, operation):
        self.stack = stack
        self.operation = operation

        # Fill variables from the environment variables
        # TODO: Merge this two variables with the parameters so we can override whatever is in the parameters.json
        self.project = os.environ.get("PROJECT", "luisc009")
        self.environment = os.environ.get("ENVIRONMENT", "dev")

        # Supportive variables
        self.stack_path = os.path.join("stacks", self.stack)
        self.stack_name = f"{self.project}-{self.stack}-{self.environment}"
        self.stack_template_file = os.path.join(self.stack_path, "template.yaml")
        self.stack_parameters_file = os.path.join(
            "env", "stacks", self.stack, f"parameters.{self.environment}.json"
        )
        self.stack_tmp_parameters_file = os.path.join("/", "tmp", "parameters.json")

        # Git variables, used to generate the change_set_name
        self.commit = Repo().head.commit.hexsha[:6]

        self.parameters = self.build_cloudformation_parameters()

    def validate_cloudformation_template(self):
        with open(self.stack_template_file, "r") as template_file:
            template_body = template_file.read()
            try:
                r = client.validate_template(TemplateBody=template_body)
            except botocore.exceptions.ClientError as error:
                logger.error("An error happened validating the template %s", error)
                sys.exit(errno.EINVAL)

    def read_file(self, file_path):
        with open(file_path, "r") as file:
            return file.read()

    def build_cloudformation_parameters(self):
        parameters = {"StackName": self.stack_name}

        # if operation is create, update
        # include template and parameters
        if self.operation in ["create", "update", "create_change_set"]:
            parameters["TemplateBody"] = self.read_file(self.stack_template_file)
            parameters["Parameters"] = json.loads(
                self.read_file(self.stack_parameters_file)
            )

        # if operation is create_change_set
        # include ChangeSetName
        if self.operation in [
            "create_change_set",
            "delete_change_set",
            "execute_change_set",
        ]:
            parameters["ChangeSetName"] = f"{self.stack_name}-{self.commit}"

        return parameters

    # creates a fresh new stack
    def create_stack(self):
        try:
            client.create_stack(**self.parameters)
        except client.exceptions.AlreadyExistsException as error:
            logger.error("Stack %s already exists", self.stack_name)
            sys.exit(errno.EPERM)
        return "stack_create_complete"

    # deletes an active stack
    def delete_stack(self):
        client.delete_stack(**self.parameters)
        return "stack_delete_complete"

    def update_stack(self):
        try:
            client.update_stack(**self.parameters)
        except botocore.exceptions.ClientError as error:
            logger.error(
                "An error occurred when updating %s, %s", self.stack_name, error
            )
            sys.exit(errno.EINVAL)
        return "stack_update_complete"

    def create_change_set(self):
        try:
            client.create_change_set(**self.parameters)
        except botocore.exceptions.ClientError as error:
            logger.error(
                "An error occurred when creating %s, %s",
                self.parameters["ChangeSetName"],
                error,
            )
            sys.exit(errno.EINVAL)
        return "change_set_create_complete"

    def delete_change_set(self):
        client.delete_change_set(**self.parameters)

    def execute_change_set(self):
        try:
            client.execute_change_set(**self.parameters)
        except client.exceptions.ChangeSetNotFoundException as error:
            logger.error(
                "Change set %s was not found", self.parameters["ChangeSetName"]
            )
            sys.exit(errno.EINVAL)
        return "stack_update_complete"

    def wait(self, waiter_name):
        logger.info("waiting for operation %s to complete", waiter_name)
        waiter = client.get_waiter(waiter_name)
        try:
            # TODO: Fix this, it should use the paremeters provided by the build_cloudformation_parameters
            parameters = {"StackName": self.stack_name}
            if "change_set" in waiter_name:
                parameters["ChangeSetName"] = f"{self.stack_name}-{self.commit}"
            waiter.wait(**parameters)
            logger.info(f"operation {operation} finished!")
        except botocore.exceptions.WaiterError as error:
            logger.error(
                "An error happened waiting for the operation %s, %s", operation, error
            )


# TODO: Support decrypt of the parameters file
# def generate_parameters(parameters_path):


def usage(info, err):
    help = """
main script helps with the creation of CloudFormation stacks.
Usage:

python main stack-name <command>

Commands to work with Stacks:

create              - Creates a new stack based on the environment and the stack name
update              - Updates an already created stack
delete              - Deletes an already created stack

Commands to work with Change Sets:

create_change_set   - Creates a new change set using the stack name and the commit's SHA as change set name
execute_change_set  - Executes the current change set
delete_change_set   - Delete the current change set

The stack-name is the name of the stack's folder inside stacks/
E.g.
python main network create
    """
    print(info)
    print(help)
    sys.exit(err)


def args_validator():
    if len(sys.argv) != 3:
        usage("Invalid number of arguments", errno.EINVAL)
    if sys.argv[2] not in OPERATIONS:
        usage(f"{sys.argv[2]} is not permitted", errno.EPERM)
    stack_path = os.path.join("stacks", sys.argv[1])
    if not os.path.exists(stack_path):
        usage(f"{stack_path} does not exist", errno.EPERM)
    try:
        os.environ["PROJECT"]
        os.environt["ENVIRONMENT"]
    except:
        logger.warning(
            "PROJECT or ENVIRONMENT are not set, falling back to default values"
        )


args_validator()
operation = sys.argv[2]

stack = Stack(sys.argv[1], sys.argv[2])

stack.validate_cloudformation_template()

if operation == "create":
    waiter_name = stack.create_stack()

if operation == "delete":
    waiter_name = stack.delete_stack()

if operation == "update":
    waiter_name = stack.update_stack()

if operation == "create_change_set":
    waiter_name = stack.create_change_set()

if operation == "delete_change_set":
    waiter_name = stack.delete_change_set()
    sys.exit(0)

if operation == "execute_change_set":
    waiter_name = stack.execute_change_set()

stack.wait(waiter_name)
