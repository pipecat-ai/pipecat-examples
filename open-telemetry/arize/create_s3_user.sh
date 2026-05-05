#!/bin/bash

# Creates an IAM user with long-lived access keys for the per-turn audio
# uploader. Long-lived (not assumed-role/STS) credentials are required so
# presigned GET URLs can stay valid up to 7 days — STS session tokens cap
# presigned URL lifetime at the session duration (≤1 hour).
#
# Usage: AWS_PROFILE=your_aws_profile ./create_s3_user.sh <BUCKET_NAME>

function usage()
{
  if [[ "$?" -ne 0 ]];then
    echo "Usage: AWS_PROFILE=your_aws_profile ./create_s3_user.sh <BUCKET_NAME>"
  fi

  # cleanup
  rm -rf s3-policy.json
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

YOUR_REGION=$(aws configure get region)
if [ -z "$YOUR_REGION" ];then
  YOUR_REGION="us-west-2"
fi

USER_NAME="pipecat-audio-uploader-for-trace"

# Create the bucket if it doesn't already exist.
# `head-bucket` returns 0 if accessible, non-zero if missing or forbidden.
if aws s3api head-bucket --bucket "${YOUR_BUCKET_NAME}" 2>/dev/null; then
  echo "~ bucket '${YOUR_BUCKET_NAME}' already exists, skipping create ~"
else
  echo "~ creating bucket '${YOUR_BUCKET_NAME}' in '${YOUR_REGION}' ~"
  if [ "${YOUR_REGION}" = "us-east-1" ]; then
    # us-east-1 must not have a LocationConstraint
    aws s3api create-bucket --bucket "${YOUR_BUCKET_NAME}" --region "${YOUR_REGION}" >/dev/null
  else
    aws s3api create-bucket \
      --bucket "${YOUR_BUCKET_NAME}" \
      --region "${YOUR_REGION}" \
      --create-bucket-configuration "LocationConstraint=${YOUR_REGION}" >/dev/null
  fi
  # Block public access by default — presigned URLs work without it.
  aws s3api put-public-access-block \
    --bucket "${YOUR_BUCKET_NAME}" \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
    >/dev/null
fi

echo "~ creating IAM user '${USER_NAME}' with PutObject + GetObject on '${YOUR_BUCKET_NAME}' ~"

aws iam create-user --user-name "${USER_NAME}" >/dev/null

# Inline policy: just PutObject + GetObject on the bucket. GetObject is
# included so the IAM user can presign GET URLs (the principal signing
# the URL must itself be allowed to perform the action).
cat > s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject"],
    "Resource": "arn:aws:s3:::${YOUR_BUCKET_NAME}/*"
  }]
}
EOF

aws iam put-user-policy \
  --user-name "${USER_NAME}" \
  --policy-name TurnAudioReadWritePolicy \
  --policy-document file://s3-policy.json

echo "-------"
echo "~ add these vars to your Pipecat Bot .env ~"
echo ""
aws iam create-access-key --user-name "${USER_NAME}" | \
  jq -r '.AccessKey | "AWS_ACCESS_KEY_ID=" + .AccessKeyId, "AWS_SECRET_ACCESS_KEY=" + .SecretAccessKey'
echo "AWS_DEFAULT_REGION=${YOUR_REGION}"
echo "AWS_BUCKET_NAME=${YOUR_BUCKET_NAME}"
echo ""
