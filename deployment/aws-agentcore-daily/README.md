# Amazon Bedrock AgentCore Runtime Daily Example

This example demonstrates how to deploy a Pipecat voice agent to **Amazon Bedrock AgentCore Runtime** using Daily as the transport. Users join by visiting a Daily room URL in their browser. The example pipeline orchestrates Deepgram (speech-to-text), Amazon Nova (LLM), and Cartesia (text-to-speech).

> **Note:** This example focuses on illustrating how to get a Pipecat bot running as an agent in AgentCore Runtime. In the interest of staying focused on that goal, it does not address various production-readiness concerns, including but not limited to: authentication with the server that launches the agent, sanitized logging, rate limiting, CORS tightening, and input validation. Be sure to address these before deploying to production.

## Prerequisites

- Accounts with:
  - AWS
  - Daily
  - Deepgram
  - Cartesia
- Python 3.10 or higher
- `uv` package manager

## Set Up the Environment

### IAM Configuration

Configure your IAM user with the necessary policies for AgentCore deployment and management:

- `BedrockAgentCoreFullAccess`
- A new policy (maybe named `BedrockAgentCoreCLI`) configured [like this](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html#runtime-permissions-starter-toolkit), with the following additional statement for VPC setup and teardown (required for Daily's UDP transport):

  ```json
  {
    "Sid": "EC2Access",
    "Effect": "Allow",
    "Action": [
      "ec2:CreateVpc",
      "ec2:CreateTags",
      "ec2:ModifyVpcAttribute",
      "ec2:CreateInternetGateway",
      "ec2:AttachInternetGateway",
      "ec2:DescribeAvailabilityZones",
      "ec2:CreateSubnet",
      "ec2:AllocateAddress",
      "ec2:CreateNatGateway",
      "ec2:DescribeNatGateways",
      "ec2:CreateRouteTable",
      "ec2:CreateRoute",
      "ec2:AssociateRouteTable",
      "ec2:CreateSecurityGroup",
      "ec2:AuthorizeSecurityGroupEgress",
      "ec2:DeleteNatGateway",
      "ec2:ReleaseAddress",
      "ec2:DetachInternetGateway",
      "ec2:DeleteInternetGateway",
      "ec2:DeleteSubnet",
      "ec2:DeleteRouteTable",
      "ec2:DeleteSecurityGroup",
      "ec2:DeleteVpc"
    ],
    "Resource": "*"
  }
  ```

You can also choose to specify more granular permissions; see [Amazon Bedrock AgentCore docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html) for more information.

To authenticate with AWS, you have two options:

1. Export environment variables:

   ```bash
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_REGION=your_region
   export AWS_DEFAULT_REGION=your_default_region
   export AWS_SESSION_TOKEN=your_session_token  # Optional: only for temporary credentials (e.g. AWS SSO, STS AssumeRole)
   ```

2. Or use AWS CLI configuration:
   ```bash
   aws configure
   ```
   This will create/update your AWS credentials file (~/.aws/credentials).

### Virtual Environment Setup

Create and activate a virtual environment:

```bash
uv sync
```

### Environment Variables Configuration

1. For the agent:

   ```bash
   cd agent
   cp env.example .env
   ```

   Add your API keys:
   - `DEEPGRAM_API_KEY`: Your Deepgram API key
   - `CARTESIA_API_KEY`: Your Cartesia API key

2. For the server:

   ```bash
   cd server
   cp env.example .env
   ```

   Add your AWS credentials and configuration:

   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
   - `AWS_SESSION_TOKEN` (optional — only needed for temporary credentials, e.g. AWS SSO or STS AssumeRole)

   Also configure:

   - `DAILY_ROOM_URL`: Your Daily room URL (e.g. `https://YOURDOMAIN.daily.co/YOURROOM`). The server passes this to the agent at invocation time and returns it to callers of `/start`.
   - `AGENT_RUNTIME_ARN`: Automatically set during agent deployment

   > You must create a Daily room beforehand via the [Daily dashboard](https://dashboard.daily.co/) or [Daily REST API](https://docs.daily.co/reference/rest-api/rooms/create-room).

## Agent Configuration

Configure your bot as an AgentCore agent:

```bash
./scripts/configure.sh
```

This script automatically:

1. Creates IAM execution role (if needed)
2. Configures container deployment with docker runtime

> Technical Note:
> Direct Code Deploy isn't used because some dependencies (like `numba`) lack `aarch64_manylinux2014` wheels.

## Before Proceeding

Just in case you've previously deployed other agents to AgentCore, ensure that you have the desired agent selected as "default" in the `agentcore` tool:

```
# Check
uv run agentcore configure list
# Set
uv run agentcore configure set-default <agent-name>
```

The following steps act on `agentcore`'s default agent.

## Deployment to AgentCore Runtime

VPC deployment is required for this example. Daily's transport relies on UDP, which is blocked in AgentCore's PUBLIC network mode. VPC mode deploys AgentCore Runtime in private subnets with a NAT Gateway for outbound internet access, enabling UDP connectivity.

```bash
# First time: Create VPC infrastructure (NAT Gateway costs ~$32/month)
# Note that this creates various Elastic IP addresses; ensure you have sufficient quota (https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html#using-instance-addressing-limit)
./scripts/setup-vpc.sh

# Deploy agent
# (This is the only command you need to run after an incremental change to your agent's code)
./scripts/launch.sh
```

**Infrastructure overview:**

- VPC with public and private subnets across 2 availability zones
- Internet Gateway for public subnet connectivity
- NAT Gateway in public subnet for private subnet outbound traffic
- Route tables directing private subnet traffic through NAT Gateway
- Security groups allowing outbound connections

The launch script:

1. Reads environment variables from `agent/.env`
2. Deploys to AgentCore
3. Updates the server's configuration with the agent ARN
4. Displays log-tailing commands for monitoring

## Running on AgentCore Runtime

1. Start the server:

   ```bash
   cd server
   uv run server.py
   ```

2. Trigger the agent:

   ```bash
   curl -X POST http://localhost:7860/start
   ```

   This invokes the agent on AgentCore and returns the Daily room URL.

3. Join the call:
   - Open the Daily room URL in your browser (the `room_url` returned by `/start`)
   - Allow microphone permissions when prompted
   - Speak to the agent -- you should hear a voice response

## Monitoring and Troubleshooting

### View Server Logs

The server (`server.py`) invokes the AgentCore agent and returns the room URL. Check the terminal where the server is already running (from step 1 above).

### View Agent Logs

Use the log-tailing command provided during deployment:

```bash
# Replace with your actual command
aws logs tail /aws/bedrock-agentcore/runtimes/bot1-0uJkkT7QHC-DEFAULT --log-stream-name-prefix "2025/11/19/[runtime-logs]" --follow
```

If you don't have that command handy, no worries. Just run:

```bash
uv run agentcore status
```

## Cleanup

Remove your agent:

```bash
./scripts/destroy.sh
```

Remove VPC resources:

```bash
./scripts/cleanup-vpc.sh
```

## Local Development

For testing, it may be helpful to run your bot locally without having to deploy to AgentCore.

First, ensure that your agent's `.env` file specifies the necessary variables for local development (placeholders should already be there, from env.example).

Then, run your bot in local dev mode:

```bash
PIPECAT_LOCAL_DEV=1 uv run pipecat-agent.py -t daily -d
```

## Additional Resources

- [Amazon Bedrock AgentCore Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [Daily Documentation](https://docs.daily.co/)
