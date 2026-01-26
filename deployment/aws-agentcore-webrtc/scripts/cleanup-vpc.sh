#!/bin/bash

# Script to cleanup VPC infrastructure for AgentCore Runtime
# Deletes VPC, subnets, NAT gateway, Internet Gateway, and security groups

set -e

###############################################
# STEP 1 — Check if VPC config exists
###############################################
if [ ! -f "vpc-config.env" ]; then
    echo "❌ Error: vpc-config.env not found"
    echo "No VPC resources to clean up"
    exit 0
fi

###############################################
# STEP 2 — Load VPC configuration
###############################################
echo "Loading VPC configuration..."
source vpc-config.env

echo ""
echo "=========================================="
echo "VPC Cleanup"
echo "=========================================="
echo ""
echo "This will delete the following resources:"
echo "  - VPC: $VPC_ID"
echo "  - Subnets: $PRIVATE_SUBNET_1, $PRIVATE_SUBNET_2, $PUBLIC_SUBNET_1, $PUBLIC_SUBNET_2"
echo "  - NAT Gateway: $NAT_GW_ID"
echo "  - Internet Gateway: $IGW_ID"
echo "  - Elastic IP: $EIP_ALLOC_ID"
echo "  - Security Group: $SG_ID"
echo ""
read -p "Are you sure you want to proceed? (yes/no): " -r
echo ""
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Cleanup cancelled"
    exit 0
fi

###############################################
# STEP 3 — Delete NAT Gateway
###############################################
echo ""
echo "Deleting NAT Gateway..."
aws ec2 delete-nat-gateway \
    --nat-gateway-id $NAT_GW_ID \
    --region $AWS_REGION

echo "✅ NAT Gateway deletion initiated (will take a few minutes)"
echo "Waiting for NAT Gateway to be deleted..."

# Wait for NAT Gateway to be deleted
aws ec2 wait nat-gateway-deleted \
    --nat-gateway-ids $NAT_GW_ID \
    --region $AWS_REGION 2>/dev/null || echo "Timeout waiting for NAT Gateway deletion (continuing...)"

###############################################
# STEP 4 — Release Elastic IP
###############################################
echo ""
echo "Releasing Elastic IP..."
aws ec2 release-address \
    --allocation-id $EIP_ALLOC_ID \
    --region $AWS_REGION

echo "✅ Elastic IP released"

###############################################
# STEP 5 — Detach and delete Internet Gateway
###############################################
echo ""
echo "Detaching Internet Gateway..."
aws ec2 detach-internet-gateway \
    --internet-gateway-id $IGW_ID \
    --vpc-id $VPC_ID \
    --region $AWS_REGION

echo "Deleting Internet Gateway..."
aws ec2 delete-internet-gateway \
    --internet-gateway-id $IGW_ID \
    --region $AWS_REGION

echo "✅ Internet Gateway deleted"

###############################################
# STEP 6 — Delete subnets
###############################################
echo ""
echo "Deleting subnets..."

aws ec2 delete-subnet \
    --subnet-id $PRIVATE_SUBNET_1 \
    --region $AWS_REGION

aws ec2 delete-subnet \
    --subnet-id $PRIVATE_SUBNET_2 \
    --region $AWS_REGION

aws ec2 delete-subnet \
    --subnet-id $PUBLIC_SUBNET_1 \
    --region $AWS_REGION

aws ec2 delete-subnet \
    --subnet-id $PUBLIC_SUBNET_2 \
    --region $AWS_REGION

echo "✅ Subnets deleted"

###############################################
# STEP 7 — Delete route tables
###############################################
echo ""
echo "Deleting route tables..."

aws ec2 delete-route-table \
    --route-table-id $PUBLIC_RT_ID \
    --region $AWS_REGION 2>/dev/null || echo "(Public route table already deleted or in use)"

aws ec2 delete-route-table \
    --route-table-id $PRIVATE_RT_ID \
    --region $AWS_REGION 2>/dev/null || echo "(Private route table already deleted or in use)"

echo "✅ Route tables deleted"

###############################################
# STEP 8 — Delete security group
###############################################
echo ""
echo "Deleting security group..."
aws ec2 delete-security-group \
    --group-id $SG_ID \
    --region $AWS_REGION

echo "✅ Security group deleted"

###############################################
# STEP 9 — Delete VPC
###############################################
echo ""
echo "Deleting VPC..."
aws ec2 delete-vpc \
    --vpc-id $VPC_ID \
    --region $AWS_REGION

echo "✅ VPC deleted"

###############################################
# STEP 10 — Clean up configuration files
###############################################
echo ""
echo "Cleaning up configuration files..."
rm -f vpc-config.env

echo ""
echo "=========================================="
echo "VPC Cleanup Complete!"
echo "=========================================="
echo ""
echo "All VPC resources have been deleted."
echo ""
echo "Note: Update .bedrock_agentcore.yaml to use PUBLIC network mode"
echo "      or run ./scripts/setup-vpc.sh to create new VPC resources."
echo ""
