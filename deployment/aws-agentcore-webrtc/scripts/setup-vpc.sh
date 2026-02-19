#!/bin/bash

# Script to create VPC infrastructure for AgentCore Runtime
# Creates VPC with public/private subnets, NAT gateway, and security groups

set -e

###############################################
# STEP 1 — Load environment variables
###############################################
if [ ! -f "./agent/.env" ]; then
    echo "❌ Error: agent/.env not found"
    exit 1
fi

echo "Loading environment variables..."
set -a
source ./agent/.env
set +a

###############################################
# STEP 2 — Create VPC
###############################################
echo ""
echo "Creating VPC..."
VPC_ID=$(aws ec2 create-vpc \
    --cidr-block 10.0.0.0/16 \
    --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=agentcore-webrtc-vpc}]' \
    --region $AWS_REGION \
    --query 'Vpc.VpcId' \
    --output text)

echo "✅ VPC created: $VPC_ID"

# Enable DNS hostnames
aws ec2 modify-vpc-attribute \
    --vpc-id $VPC_ID \
    --enable-dns-hostnames \
    --region $AWS_REGION

###############################################
# STEP 3 — Create Internet Gateway
###############################################
echo ""
echo "Creating Internet Gateway..."
IGW_ID=$(aws ec2 create-internet-gateway \
    --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=agentcore-webrtc-igw}]' \
    --region $AWS_REGION \
    --query 'InternetGateway.InternetGatewayId' \
    --output text)

aws ec2 attach-internet-gateway \
    --vpc-id $VPC_ID \
    --internet-gateway-id $IGW_ID \
    --region $AWS_REGION

echo "✅ Internet Gateway created and attached: $IGW_ID"

###############################################
# STEP 4 — Create Subnets
###############################################
echo ""
echo "Creating subnets..."

# Get first two availability zones for the region
AZ1=$(aws ec2 describe-availability-zones \
    --region $AWS_REGION \
    --query 'AvailabilityZones[0].ZoneName' \
    --output text)

AZ2=$(aws ec2 describe-availability-zones \
    --region $AWS_REGION \
    --query 'AvailabilityZones[1].ZoneName' \
    --output text)

echo "Using Availability Zones: $AZ1, $AZ2"

# Create public subnet 1
PUBLIC_SUBNET_1=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.1.0/24 \
    --availability-zone $AZ1 \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=agentcore-public-subnet-1}]' \
    --region $AWS_REGION \
    --query 'Subnet.SubnetId' \
    --output text)

# Create public subnet 2
PUBLIC_SUBNET_2=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.2.0/24 \
    --availability-zone $AZ2 \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=agentcore-public-subnet-2}]' \
    --region $AWS_REGION \
    --query 'Subnet.SubnetId' \
    --output text)

# Create private subnet 1
PRIVATE_SUBNET_1=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.11.0/24 \
    --availability-zone $AZ1 \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=agentcore-private-subnet-1}]' \
    --region $AWS_REGION \
    --query 'Subnet.SubnetId' \
    --output text)

# Create private subnet 2
PRIVATE_SUBNET_2=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.12.0/24 \
    --availability-zone $AZ2 \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=agentcore-private-subnet-2}]' \
    --region $AWS_REGION \
    --query 'Subnet.SubnetId' \
    --output text)

echo "✅ Public Subnets: $PUBLIC_SUBNET_1, $PUBLIC_SUBNET_2"
echo "✅ Private Subnets: $PRIVATE_SUBNET_1, $PRIVATE_SUBNET_2"

###############################################
# STEP 5 — Allocate Elastic IP for NAT Gateway
###############################################
echo ""
echo "Allocating Elastic IP for NAT Gateway..."
EIP_ALLOC_ID=$(aws ec2 allocate-address \
    --domain vpc \
    --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=agentcore-nat-eip}]' \
    --region $AWS_REGION \
    --query 'AllocationId' \
    --output text)

echo "✅ Elastic IP allocated: $EIP_ALLOC_ID"

###############################################
# STEP 6 — Create NAT Gateway
###############################################
echo ""
echo "Creating NAT Gateway (this may take a few minutes)..."
NAT_GW_ID=$(aws ec2 create-nat-gateway \
    --subnet-id $PUBLIC_SUBNET_1 \
    --allocation-id $EIP_ALLOC_ID \
    --tag-specifications 'ResourceType=natgateway,Tags=[{Key=Name,Value=agentcore-nat-gateway}]' \
    --region $AWS_REGION \
    --query 'NatGateway.NatGatewayId' \
    --output text)

echo "✅ NAT Gateway created: $NAT_GW_ID"
echo "Waiting for NAT Gateway to become available..."

aws ec2 wait nat-gateway-available \
    --nat-gateway-ids $NAT_GW_ID \
    --region $AWS_REGION

echo "✅ NAT Gateway is now available"

###############################################
# STEP 7 — Create Route Tables
###############################################
echo ""
echo "Creating route tables..."

# Create public route table
PUBLIC_RT_ID=$(aws ec2 create-route-table \
    --vpc-id $VPC_ID \
    --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=agentcore-public-rt}]' \
    --region $AWS_REGION \
    --query 'RouteTable.RouteTableId' \
    --output text)

# Add route to Internet Gateway
aws ec2 create-route \
    --route-table-id $PUBLIC_RT_ID \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id $IGW_ID \
    --region $AWS_REGION

# Associate public subnets with public route table
aws ec2 associate-route-table \
    --subnet-id $PUBLIC_SUBNET_1 \
    --route-table-id $PUBLIC_RT_ID \
    --region $AWS_REGION

aws ec2 associate-route-table \
    --subnet-id $PUBLIC_SUBNET_2 \
    --route-table-id $PUBLIC_RT_ID \
    --region $AWS_REGION

echo "✅ Public route table created: $PUBLIC_RT_ID"

# Create private route table
PRIVATE_RT_ID=$(aws ec2 create-route-table \
    --vpc-id $VPC_ID \
    --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=agentcore-private-rt}]' \
    --region $AWS_REGION \
    --query 'RouteTable.RouteTableId' \
    --output text)

# Add route to NAT Gateway
aws ec2 create-route \
    --route-table-id $PRIVATE_RT_ID \
    --destination-cidr-block 0.0.0.0/0 \
    --nat-gateway-id $NAT_GW_ID \
    --region $AWS_REGION

# Associate private subnets with private route table
aws ec2 associate-route-table \
    --subnet-id $PRIVATE_SUBNET_1 \
    --route-table-id $PRIVATE_RT_ID \
    --region $AWS_REGION

aws ec2 associate-route-table \
    --subnet-id $PRIVATE_SUBNET_2 \
    --route-table-id $PRIVATE_RT_ID \
    --region $AWS_REGION

echo "✅ Private route table created: $PRIVATE_RT_ID"

###############################################
# STEP 8 — Create Security Groups
###############################################
echo ""
echo "Creating security groups..."

# Create security group for AgentCore Runtime
SG_ID=$(aws ec2 create-security-group \
    --group-name agentcore-webrtc-sg \
    --description "Security group for AgentCore WebRTC runtime" \
    --vpc-id $VPC_ID \
    --tag-specifications 'ResourceType=security-group,Tags=[{Key=Name,Value=agentcore-webrtc-sg}]' \
    --region $AWS_REGION \
    --query 'GroupId' \
    --output text)

# Allow all outbound traffic (default for security groups)
# Allow HTTPS outbound to AWS services
aws ec2 authorize-security-group-egress \
    --group-id $SG_ID \
    --ip-permissions IpProtocol=-1,FromPort=-1,ToPort=-1,IpRanges='[{CidrIp=0.0.0.0/0}]' \
    --region $AWS_REGION 2>/dev/null || true

echo "✅ Security group created: $SG_ID"

###############################################
# STEP 9 — Update .bedrock_agentcore.yaml
###############################################
echo ""
echo "Updating .bedrock_agentcore.yaml with VPC configuration..."

# Backup the original file
cp .bedrock_agentcore.yaml .bedrock_agentcore.yaml.backup

# Update network configuration using sed (preserves formatting better than Python YAML)
sed -i.tmp "s/network_mode: PUBLIC/network_mode: VPC/" .bedrock_agentcore.yaml
sed -i.tmp "s/network_mode_config: null/network_mode_config:\\
          subnets:\\
            - $PRIVATE_SUBNET_1\\
            - $PRIVATE_SUBNET_2\\
          security_groups:\\
            - $SG_ID/" .bedrock_agentcore.yaml

# Clean up temp file
rm -f .bedrock_agentcore.yaml.tmp

echo "✅ Configuration updated (backup saved as .bedrock_agentcore.yaml.backup)"

###############################################
# STEP 10 — Save VPC configuration
###############################################
echo ""
echo "Saving VPC configuration to vpc-config.env..."

cat > vpc-config.env << EOF
# VPC Configuration for AgentCore Runtime
# Generated by setup-vpc.sh on $(date)

VPC_ID=$VPC_ID
IGW_ID=$IGW_ID
NAT_GW_ID=$NAT_GW_ID
EIP_ALLOC_ID=$EIP_ALLOC_ID

PUBLIC_SUBNET_1=$PUBLIC_SUBNET_1
PUBLIC_SUBNET_2=$PUBLIC_SUBNET_2
PRIVATE_SUBNET_1=$PRIVATE_SUBNET_1
PRIVATE_SUBNET_2=$PRIVATE_SUBNET_2

PUBLIC_RT_ID=$PUBLIC_RT_ID
PRIVATE_RT_ID=$PRIVATE_RT_ID

SG_ID=$SG_ID

AWS_REGION=$AWS_REGION
EOF

echo "✅ VPC configuration saved"

###############################################
# STEP 11 — Summary
###############################################
echo ""
echo "=========================================="
echo "VPC Infrastructure Created Successfully!"
echo "=========================================="
echo ""
echo "VPC ID: $VPC_ID"
echo "Private Subnets: $PRIVATE_SUBNET_1, $PRIVATE_SUBNET_2"
echo "Public Subnets: $PUBLIC_SUBNET_1, $PUBLIC_SUBNET_2"
echo "NAT Gateway: $NAT_GW_ID"
echo "Security Group: $SG_ID"
echo ""
echo "Configuration saved to:"
echo "  - .bedrock_agentcore.yaml (updated)"
echo "  - vpc-config.env (for reference)"
echo ""
echo "Next step: Run ./scripts/launch.sh to deploy to VPC"
echo ""
