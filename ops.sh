#!/usr/bin/env bash
export Environment=${Environment:-dev}
export Project="${Project:-luisc09}"

_validatecf() {
  aws cloudformation validate-template \
    --template-body file://"$stack_template_path" > log 2>&1
  _checkStatusCode $? "Template validation: failed" "Template validation: succeeded"
}

_waitcf() {
  printf "\nWaiting for %s" "$operation"
  aws cloudformation wait stack-"$operation"-complete --stack-name "$stack_name" > log 2>&1
  _checkStatusCode $? "Operation $operation: failed; go to https://console.aws.amazon.com/cloudformation/home and check the status of the stack" "Operation $operation: succeeded"
}

_waitChangeSet() {
  printf "\nWaiting for %s" "$operation"
  aws cloudformation wait change-set-create-complete --stack-name "$stack_name" --change-set-name "$changesetname" > log 2>&1
  _checkStatusCode $? "Operation $operation: failed; go to https://console.aws.amazon.com/cloudformation/home and check the status of the stack" "Operation $operation: succeeded"
}

_clean(){
  rm -rf "$stack_tmp_parameters_file"
}

_generateParameters(){
  file=$(find "$stack_parameters_path" -name "parameters*${Environment}*")
  if [ "${file##*.}" = "enc" ]; then
    sops -d "$file" > "$stack_tmp_parameters_file" > log 2>&1 || return 1
  else
    cp "$file" "$stack_tmp_parameters_file" > log 2>&1 || return 1
  fi
  return 0
}

_checkStatusCode(){
  if [[ $1 != 0 ]]; then
    printf "\n%s\nPlease check the log file" "$2"
    exit "$1"
  else
    printf "\n%s" "$3"
  fi
}

create() {
  aws cloudformation create-stack --stack-name "$stack_name" \
    --template-body file://"$stack_template_path"  \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameters file://"$stack_tmp_parameters_file" > log 2>&1
}

update() {
  aws cloudformation update-stack --stack-name "$stack_name" \
    --template-body file://"$stack_template_path"  \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameters file://"$stack_tmp_parameters_file" > log 2>&1
}

delete() {
  aws cloudformation delete-stack --stack-name "$stack_name" > log 2>&1
}

create_change_set() {
  aws cloudformation create-change-set --stack-name "$stack_name" \
    --change-set-name $changesetname \
    --template-body file://"$stack_template_path" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameters file://"$stack_tmp_parameters_file" > log 2>&1
}

usage() {
  cat <<EOF
  ops script helps with the creation of CloudFormation stacks.
  Usage:

    ./ops.sh stack-name <command>

  Commands:
    create            - Starts the creation of the stack.
    create_change_set - Starts the creation of one Change set
    update            - Starts the update on an already created stack.
    delete            - Starts to delete an already created stack.

  The stack-name is the name of the folder inside stacks/
  E.g.
    ./ops.sh network create
EOF
}
#Set variables from the arguments.
stack=$1
operation=$2
stack_path="stacks/${stack}"
stack_name="$Project-$stack-$Environment"
stack_template_path="$stack_path/template.yaml"
stack_parameters_path="env/stacks/${stack}"
stack_tmp_parameters_file="/tmp/parameters.json"

if [[ $operation == "" ]]; then
    usage
  else
    case $operation in
      create|update|delete)
        _validatecf
        _generateParameters
        _checkStatusCode $? "Parameters validation: failed" "Parameters validation: succeeded"
        "$operation"
        _checkStatusCode $? "Requested operation $operation: failed" "Requested operation $operation: succeeded"
        _waitcf
        _clean
        ;;
      create_change_set)
        _validatecf
        _generateParameters
        _checkStatusCode $? "Parameters validation: failed" "Parameters validation: succeeded"
        changesetname=$stack_name"-$(date +'%s')"
        "$operation"
        _waitChangeSet
        _clean
        exit 0
        ;;
      *) usage
         exit 2
        ;;
    esac
fi
