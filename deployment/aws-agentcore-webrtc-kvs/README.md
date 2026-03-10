# Amazon Bedrock AgentCore Runtime WebRTC Example (KVS Managed TURN)

This example demonstrates how to deploy a Pipecat voice agent to **Amazon Bedrock AgentCore Runtime** using SmallWebRTC as a lightweight transport mechanism, with **Amazon Kinesis Video Streams (KVS)** providing managed TURN infrastructure entirely within AWS. The example pipeline orchestrates Deepgram (speech-to-text), Amazon Nova (LLM), and Cartesia (text-to-speech).

> **Note:** This example focuses on illustrating how to get a Pipecat bot running as an agent in AgentCore Runtime. In the interest of staying focused on that goal, it does not address various production-readiness concerns, including but not limited to: authentication with the server that launches the agent, sanitized logging, rate limiting, CORS tightening, and input validation. Be sure to address these before deploying to production.

## How KVS Managed TURN Works

Instead of configuring non-AWS TURN providers, this example uses [Amazon Kinesis Video Streams (KVS)](https://docs.aws.amazon.com/kinesisvideostreams/latest/dg/what-is-amazon-kinesis-video-streams.html) for managed TURN infrastructure. KVS provides temporary, auto-rotating TURN credentials through the [GetIceServerConfig](https://docs.aws.amazon.com/kinesisvideostreams/latest/dg/API_signaling_GetIceServerConfig.html) API, eliminating non-AWS dependencies for NAT traversal.

The flow works as follows:

1. **One-time setup:** A KVS signaling channel is created (automatically on first connection, or via CLI). The channel is used only for TURN credential provisioning -- your agent continues to use Pipecat's WebRTC transport for all signaling and media.
2. **At connection time:** Your agent calls `GetSignalingChannelEndpoint` to get the HTTPS endpoint, then calls `GetIceServerConfig` to retrieve temporary TURN credentials (URIs, username, password).
3. **Configure the peer connection:** The returned credentials are passed to the WebRTC peer connection as ICE servers. TURN traffic flows through KVS-managed infrastructure.

### Choosing Between KVS and Non-AWS TURN

| Factor | KVS Managed TURN (this example) | Non-AWS TURN |
|---|---|---|
| AWS-native | Yes -- no external dependency | No -- requires external account |
| Credential management | Automatic rotation | Manual or provider-managed |
| Setup | Create signaling channel + API calls | Configure environment variables |
| Best for | AWS-centric deployments | Simplicity or existing provider relationships |

> For the non-AWS TURN variant, see the [`aws-agentcore-webrtc`](../aws-agentcore-webrtc) example.

## Prerequisites

- Accounts with:
  - AWS
  - Deepgram
  - Cartesia
- Python 3.10 or higher
- `uv` package manager

## Set Up the Environment

### IAM Configuration

Configure your IAM user with the necessary policies for AgentCore deployment and management:

- `BedrockAgentCoreFullAccess`
- A new policy (maybe named `BedrockAgentCoreCLI`) configured [like this](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html#runtime-permissions-starter-toolkit), with the following additional statements:

  **EC2 access** (for VPC setup and teardown):
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

  **KVS access** (for signaling channel creation):
  ```json
  {
    "Sid": "KVSAccess",
    "Effect": "Allow",
    "Action": [
      "kinesisvideo:CreateSignalingChannel",
      "kinesisvideo:DescribeSignalingChannel",
      "kinesisvideo:DeleteSignalingChannel",
      "kinesisvideo:GetSignalingChannelEndpoint",
      "kinesisvideo:GetIceServerConfig"
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
   - `KVS_CHANNEL_NAME`: Name of the KVS signaling channel for TURN credentials (default: `voice-agent-turn`)

   > No TURN server URLs or credentials are needed -- KVS provides these automatically.

2. For the server:

   ```bash
   cd server
   cp env.example .env
   ```

   Add your AWS credentials and configuration:

   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
   - `AWS_SESSION_TOKEN` (optional -- only needed for temporary credentials, e.g. AWS SSO or STS AssumeRole)

   Also configure:

   - `AGENT_RUNTIME_ARN`: Automatically set during agent deployment
   - `KVS_CHANNEL_NAME`: Must match the agent configuration

   > **KVS permissions:** The AWS account running the server also needs KVS permissions (`kinesisvideo:DescribeSignalingChannel`, `GetSignalingChannelEndpoint`, `GetIceServerConfig`) to fetch TURN credentials for the browser client. The same KVS IAM policy listed above applies here.

### KVS Signaling Channel Setup (Optional)

The signaling channel is auto-created on first connection. To create it ahead of time:

```bash
aws kinesisvideo create-signaling-channel \
  --channel-name voice-agent-turn \
  --channel-type SINGLE_MASTER \
  --region us-west-2
```

## Agent Configuration

Configure your bot as an AgentCore agent:

```bash
./scripts/configure.sh
```

This script automatically:

1. Creates IAM execution role (if needed) with Bedrock and KVS permissions
2. Configures container deployment with docker runtime
3. Patches Dockerfile to add SmallWebRTC dependencies (`libgl1` and `libglib2.0-0`)

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

**VPC Mode (recommended) - TCP and UDP TURN support:**

```bash
# First time: Create VPC infrastructure (NAT Gateway costs ~$32/month)
# Note that this creates various Elastic IP addresses; ensure you have sufficient quota (https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html#using-instance-addressing-limit)
./scripts/setup-vpc.sh

# Deploy agent
# (This is the only command you need to run after an incremental change to your agent's code)
./scripts/launch.sh
```

This deploys AgentCore Runtime in private subnets with NAT Gateway for outbound internet access, enabling UDP TURN relay (blocked in PUBLIC mode) for better WebRTC connection reliability, lower latency, and enhanced security with private subnet isolation.

**Infrastructure overview:**

- VPC with public and private subnets across 2 availability zones
- Internet Gateway for public subnet connectivity
- NAT Gateway in public subnet for private subnet outbound traffic
- Route tables directing private subnet traffic through NAT Gateway
- Security groups allowing outbound HTTPS and UDP connections

**PUBLIC Mode - TCP TURN only:**

For development/testing without UDP TURN:

```bash
./scripts/launch.sh
```

The launch script:

1. Reads environment variables from `agent/.env`
2. Deploys to AgentCore
3. Updates the server's configuration with the agent ARN
4. Displays log-tailing commands for monitoring

> **Note on KVS and VPC:** KVS TURN endpoints do not support PrivateLink, so the VPC still requires internet egress (via NAT Gateway) to reach KVS TURN endpoints.

## Running on AgentCore Runtime

1. Start the server:

   ```bash
   cd server
   uv run server.py
   ```

2. Access the UI:
   - Open http://localhost:7860 in your browser
   - Or use your configured custom port

3. Test WebRTC connectivity:
   - Click "Connect" in the UI
   - Allow microphone permissions when prompted
   - Speak to the agent - you should hear a voice response
   - Verify connection type:
     - Open browser DevTools (F12 -> Console tab)
     - Type `chrome://webrtc-internals` in address bar (Chrome) or `about:webrtc` (Firefox) for detailed stats
     - Look for "Selected candidate pair" showing protocol (`udp` for VPC, `tcp` for PUBLIC) and type (`relay` for TURN)
   - For log monitoring, see the next section below

## KVS Considerations

- **Cost:** Each active signaling channel costs $0.03/month. At low to moderate volume, this is negligible.
- **Rate limit:** `GetIceServerConfig` is limited to 5 transactions per second (TPS) per channel. For high-volume deployments exceeding 100,000 sessions per month, implement a channel pooling strategy where you distribute requests across multiple channels: `channels_needed = ceil(peak_new_sessions_per_second / 5)`.
- **No PrivateLink:** The VPC still requires internet egress (via NAT Gateway) to reach KVS TURN endpoints.
- **Credential lifetime:** KVS TURN credentials are temporary and auto-rotated, so you do not need to manage credential rotation.

## Monitoring and Troubleshooting

### View Intermediary Server Logs

The intermediary server (`server.py`) proxies WebRTC signaling between the browser client and AgentCore Runtime. Check the terminal where the server is already running (from step 1 above).

Look for:

- WebRTC SDP offers and answers
- ICE candidate exchanges showing protocol (`udp`/`tcp`) and type (`relay`/`host`)
- KVS TURN credential retrieval logs
- Connection events and errors

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

## Test Agent Manually

Test the agent using the AWS CLI:

```bash
uv run agentcore invoke \
  --session-id user-123456-conversation-12345679 \
  '{
  "sdp": "YOUR_OFFER",
  "type": "offer"
}'
```

> This will only allow you to see that the Pipecat agent has started, but you won't be able to hear or send audio. So it is only useful for troubleshooting.

## Cleanup

Remove your agent:

```bash
./scripts/destroy.sh
```

If using VPC mode, remove VPC resources:

```bash
./scripts/cleanup-vpc.sh
```

Optionally, delete the KVS signaling channel:

```bash
aws kinesisvideo delete-signaling-channel \
  --channel-arn $(aws kinesisvideo describe-signaling-channel \
    --channel-name voice-agent-turn \
    --query 'ChannelInfo.ChannelARN' \
    --output text) \
  --region us-west-2
```

## Local Development

For testing, it may be helpful to run your bot locally without having to deploy to AgentCore.

First, ensure that your agent's `.env` file specifies the necessary variables for local development (placeholders should already be there, from env.example).

Then, run your bot in local dev mode:

```bash
PIPECAT_LOCAL_DEV=1 uv run pipecat-agent.py
```

## Additional Resources

- [Amazon Bedrock AgentCore Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [Amazon Kinesis Video Streams Developer Guide](https://docs.aws.amazon.com/kinesisvideostreams/latest/dg/what-is-amazon-kinesis-video-streams.html)
- [GetIceServerConfig API Reference](https://docs.aws.amazon.com/kinesisvideostreams/latest/dg/API_signaling_GetIceServerConfig.html)
