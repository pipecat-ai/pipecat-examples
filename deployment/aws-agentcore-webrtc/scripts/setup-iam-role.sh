#!/bin/bash

# Script to create IAM execution role for AgentCore with Bedrock permissions
# This role will be used by AgentCore Runtime to access Bedrock models and ECR

set -e

# Load AWS region from agent/.env
if [ ! -f "./agent/.env" ]; then
    echo "❌ Error: agent/.env not found"
    exit 1
fi

source ./agent/.env

ROLE_NAME="AmazonBedrockAgentCoreSDKRuntime-${AWS_REGION}-webrtc"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Creating IAM execution role for AgentCore..."
echo "Account: $ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo "Role Name: $ROLE_NAME"
echo ""

###############################################
# STEP 1 — Create trust policy
###############################################
cat > /tmp/trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "bedrock-agentcore.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

###############################################
# STEP 2 — Create IAM role
###############################################
echo "Creating IAM role..."

aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document file:///tmp/trust-policy.json \
    --description "Execution role for AgentCore Runtime with Bedrock and ECR access" \
    2>/dev/null || echo "Role already exists, continuing..."

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "✅ Role ARN: $ROLE_ARN"

###############################################
# STEP 3 — Attach ECR read-only policy
###############################################
echo ""
echo "Attaching ECR read-only policy..."

aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly \
    2>/dev/null || echo "Policy already attached"

echo "✅ ECR permissions added"

###############################################
# STEP 4 — Create and attach runtime permissions policy
###############################################
echo ""
echo "Creating AgentCore runtime permissions policy..."

cat > /tmp/runtime-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ECRImageAccess",
            "Effect": "Allow",
            "Action": [
                "ecr:BatchGetImage",
                "ecr:GetDownloadUrlForLayer"
            ],
            "Resource": [
                "arn:aws:ecr:${AWS_REGION}:${ACCOUNT_ID}:repository/*"
            ]
        },
        {
            "Sid": "ECRTokenAccess",
            "Effect": "Allow",
            "Action": [
                "ecr:GetAuthorizationToken"
            ],
            "Resource": "*"
        },
        {
            "Sid": "CloudWatchLogsDescribe",
            "Effect": "Allow",
            "Action": [
                "logs:DescribeLogStreams",
                "logs:CreateLogGroup"
            ],
            "Resource": [
                "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/runtimes/*"
            ]
        },
        {
            "Sid": "CloudWatchLogsGroupDescribe",
            "Effect": "Allow",
            "Action": [
                "logs:DescribeLogGroups"
            ],
            "Resource": [
                "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:*"
            ]
        },
        {
            "Sid": "CloudWatchLogsWrite",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": [
                "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
            ]
        },
        {
            "Sid": "XRayTracing",
            "Effect": "Allow",
            "Action": [
                "xray:PutTraceSegments",
                "xray:PutTelemetryRecords",
                "xray:GetSamplingRules",
                "xray:GetSamplingTargets"
            ],
            "Resource": "*"
        },
        {
            "Sid": "CloudWatchMetrics",
            "Effect": "Allow",
            "Action": "cloudwatch:PutMetricData",
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "cloudwatch:namespace": "bedrock-agentcore"
                }
            }
        },
        {
            "Sid": "GetAgentAccessToken",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
            ],
            "Resource": [
                "arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:workload-identity-directory/default",
                "arn:aws:bedrock-agentcore:${AWS_REGION}:${ACCOUNT_ID}:workload-identity-directory/default/workload-identity/*"
            ]
        },
        {
            "Sid": "BedrockModelInvocation",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/*",
                "arn:aws:bedrock:${AWS_REGION}:${ACCOUNT_ID}:*"
            ]
        }
    ]
}
EOF

aws iam put-role-policy \
    --role-name $ROLE_NAME \
    --policy-name AgentCoreRuntimePolicy \
    --policy-document file:///tmp/runtime-policy.json

echo "✅ AgentCore runtime permissions added"

###############################################
# STEP 5 — Clean up temp files
###############################################
rm -f /tmp/trust-policy.json /tmp/bedrock-policy.json

###############################################
# STEP 6 — Summary
###############################################
echo ""
echo "=========================================="
echo "IAM Role Created Successfully!"
echo "=========================================="
echo ""
echo "Role Name: $ROLE_NAME"
echo "Role ARN: $ROLE_ARN"
echo ""
echo "Permissions:"
echo "  ✅ ECR read-only access (for pulling container images)"
echo "  ✅ Bedrock model invocation (for LLM inference)"
echo ""
echo "Next step: Update configure.sh to use this role:"
echo "  agentcore configure -e ./agent/pipecat-agent.py \\"
echo "    --name pipecat_agent \\"
echo "    --container-runtime docker \\"
echo "    --disable-memory \\"
echo "    --execution-role $ROLE_ARN"
echo ""
