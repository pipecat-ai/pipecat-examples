#!/bin/bash

function usage()
{
  if [[ "$?" -ne 0 ]];then
    echo "Usage: AWS_PROFILE=your_aws_profile ./create_s3_role.sh <BUCKET_NAME>"
  fi

  # cleanup
  rm -rf trust-policy.json
  rm -rf s3-policy.json
  rm -rf assume-policy.json
}
trap "usage" EXIT

has_jq=$(which jq)
if [ -z "$has_jq" ];then
  echo "Please install 'jq'. https://jqlang.org/download/"
  exit 1
fi

if [ -z "$1" ];then
  echo "Please pass in BUCKET_NAME."
  exit 1
else
  YOUR_BUCKET_NAME=$1
fi

YOUR_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

if [[ 12 -ne ${#YOUR_ACCOUNT_ID} ]];then
  echo "Please set AWS_PROFILE."
  exit 1
fi

# ok, looks like we have everything we need to create an assume role:
echo "~ creating role policy for '${YOUR_BUCKET_NAME}' s3 bucket ~"

# thx claude
# Create trust policy for your primary account/user
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"AWS": "arn:aws:iam::${YOUR_ACCOUNT_ID}:root"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name PipecatS3Upload \
  --assume-role-policy-document file://trust-policy.json

# Attach S3 permissions (scope to bucket)
cat > s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject"],
    "Resource": "arn:aws:s3:::${YOUR_BUCKET_NAME}/*"
  }]
}
EOF

aws iam put-role-policy \
  --role-name PipecatS3Upload \
  --policy-name S3UploadPolicy \
  --policy-document file://s3-policy.json

ARN=$(aws iam get-role --role-name PipecatS3Upload --query "Role.Arn" --output text)

# now that ARN is created, create an AssumeRole to use it
aws iam create-user --user-name pipecat-assume-role-for-s3-upload

# Attach inline policy allowing only AssumeRole
cat > assume-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "sts:AssumeRole",
    "Resource": "${ARN}"
  }]
}
EOF

aws iam put-user-policy \
  --user-name pipecat-assume-role-for-s3-upload \
  --policy-name AssumeRoleOnly \
  --policy-document file://assume-policy.json

echo "-------"
echo "~ add these vars to your Pipecat Bot .env ~"
echo ""
aws iam create-access-key --user-name pipecat-assume-role-for-s3-upload | \
  jq -r '.AccessKey | "AWS_ACCESS_KEY_ID=" + .AccessKeyId, "AWS_SECRET_ACCESS_KEY=" + .SecretAccessKey'
echo "AWS_ROLE_ARN=${ARN}"
echo ""
