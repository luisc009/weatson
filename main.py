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
# 3. Find a way better way to init the variables configuration
# 4. Find a better way to call validate and call the operations
# 8. Improve the way that waiter is called.
# 9. Improve the name of the read_file function


def validate_cloudformation_template(template_path):
    with open(template_path, "r") as template_file:
        template_body = template_file.read()
        try:
            r = client.validate_template(TemplateBody=template_body)
        except botocore.exceptions.ClientError as error:
            logger.error("An error happened validating the template %s", error)
            sys.exit(errno.EINVAL)


def read_file(file_path):
    with open(file_path, "r") as file:
        return file.read()


def build_cloudformation_parameters(stack_name, **kwargs):
    parameters = {"StackName": stack_name}
    if "change_set_name" in kwargs and kwargs.get("change_set_name") is not None:
        parameters["ChangeSetName"] = kwargs.get("change_set_name")
    if "template_path" in kwargs:
        parameters["TemplateBody"] = read_file(kwargs.get("template_path"))
    if "parameters_path" in kwargs:
        parameters["Parameters"] = json.loads(read_file(kwargs.get("parameters_path")))
    return parameters


# TODO: Support decrypt of the parameters file
# def generate_parameters(parameters_path):

# creates a fresh new stack
def create_stack(stack_name, template_path, parameters_path):
    parameters = build_cloudformation_parameters(
        stack_name, template_path=template_path, parameters_path=parameters_path
    )
    try:
        client.create_stack(**parameters)
    except client.exceptions.AlreadyExistsException as error:
        logger.error("Stack %s already exists", stack_name)
        sys.exit(errno.EPERM)
    return "stack_create_complete"


# deletes an active stack
def delete_stack(stack_name):
    parameters = build_cloudformation_parameters(stack_name)
    client.delete_stack(**parameters)
    return "stack_delete_complete"


def update_stack(stack_name, template_path, parameters_path):
    parameters = build_cloudformation_parameters(
        stack_name, template_path=template_path, parameters_path=parameters_path
    )
    try:
        client.update_stack(**parameters)
    except botocore.exceptions.ClientError as error:
        logger.error("An error occurred when updating %s, %s", stack_name, error)
        sys.exit(errno.EINVAL)
    return "stack_update_complete"


def create_change_set(stack_name, change_set_name, template_path, parameters_path):
    parameters = build_cloudformation_parameters(
        stack_name,
        change_set_name=change_set_name,
        template_path=template_path,
        parameters_path=parameters_path,
    )
    try:
        client.create_change_set(**parameters)
    except botocore.exceptions.ClientError as error:
        logger.error("An error occurred when creating %s, %s", change_set_name, error)
        sys.exit(errno.EINVAL)
    return "change_set_create_complete"


def delete_change_set(stack_name, change_set_name):
    parameters = build_cloudformation_parameters(
        stack_name, change_set_name=change_set_name
    )
    client.delete_change_set(**parameters)


def execute_change_set(stack_name, change_set_name):
    parameters = build_cloudformation_parameters(
        stack_name, change_set_name=change_set_name
    )
    try:
        client.execute_change_set(**parameters)
    except client.exceptions.ChangeSetNotFoundException as error:
        logger.error("Change set %s was not found", change_set_name)
        sys.exit(errno.EINVAL)
    return "stack_update_complete"


def wait(stack_name, waiter_name, change_set_name=None):
    logger.info("waiting for operation %s to complete", waiter_name)
    parameters = build_cloudformation_parameters(
        stack_name, change_set_name=change_set_name
    )
    waiter = client.get_waiter(waiter_name)
    try:
        waiter.wait(**parameters)
        logger.info(f"operation {operation} finished!")
    except botocore.exceptions.WaiterError as error:
        logger.error(
            "An error happened waiting for the operation %s, %s", operation, error
        )


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

# TODO: Merge this two variables with the parameters so we can override whatever is in the parameters.json
project = os.environ.get("PROJECT", "luisc009")
environment = os.environ.get("ENVIRONMENT", "dev")


stack = sys.argv[1]
operation = sys.argv[2]
stack_path = os.path.join("stacks", stack)
stack_name = f"{project}-{stack}-{environment}"
stack_template_file = os.path.join(stack_path, "template.yaml")
stack_parameters_file = os.path.join(
    "env", "stacks", stack, f"parameters.{environment}.json"
)
stack_tmp_parameters_file = os.path.join("/", "tmp", "parameters.json")

validate_cloudformation_template(stack_template_file)

repo = Repo()
commit = repo.head.commit.hexsha[:6]
change_set_name = None

if operation == "create":
    waiter_name = create_stack(stack_name, stack_template_file, stack_parameters_file)

if operation == "delete":
    waiter_name = delete_stack(stack_name)

if operation == "update":
    waiter_name = update_stack(stack_name, stack_template_file, stack_parameters_file)

if operation == "create_change_set":
    change_set_name = f"{stack_name}-{commit}"
    waiter_name = create_change_set(
        stack_name,
        change_set_name,
        stack_template_file,
        stack_parameters_file,
    )

if operation == "delete_change_set":
    change_set_name = f"{stack_name}-{commit}"
    waiter_name = delete_change_set(stack_name, change_set_name)
    sys.exit(0)

if operation == "execute_change_set":
    change_set_name = f"{stack_name}-{commit}"
    waiter_name = execute_change_set(stack_name, change_set_name)
    change_set_name = None

wait(stack_name, waiter_name, change_set_name)
