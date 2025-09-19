# Pipecat Phone Chatbot Examples

This directory contains examples for building phone chatbots using Pipecat. All examples can be run locally for development or deployed to [Pipecat Cloud](https://pipecat.daily.co) for production.

## Examples

- **[daily-pstn-dial-in](./daily-pstn-dial-in/)** - Basic incoming call handling with Daily PSTN
- **[daily-pstn-dial-out](./daily-pstn-dial-out/)** - Basic outgoing call handling with Daily PSTN
- **[daily-pstn-cold-transfer](./daily-pstn-cold-transfer/)** - Customer support bot with cold transfer to human operators
- **[daily-twilio-sip-dial-in](./daily-twilio-sip-dial-in/)** - Incoming calls using Daily + Twilio SIP
- **[daily-twilio-sip-dial-out](./daily-twilio-sip-dial-out/)** - Outgoing calls using Daily + Twilio SIP

Each example includes its own README with detailed setup instructions, architecture details, and deployment guidance.

## Getting Started

1. Choose an example that matches your use case
2. Follow the setup instructions in that example's README
3. Test locally using ngrok for webhook endpoints
4. Deploy to [Pipecat Cloud](https://pipecat.daily.co) for production

## Architecture

All examples use:

- **Transport**: Daily WebRTC
- **Speech-to-Text**: Deepgram
- **LLM**: OpenAI GPT-4o
- **Text-to-Speech**: Cartesia
- **Phone Numbers**: Daily PSTN or Twilio SIP

## Support

For questions or advanced use cases, join our [Discord community](https://discord.gg/pipecat).
