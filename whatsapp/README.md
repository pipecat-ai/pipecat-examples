# WhatsApp WebRTC Bot

A real-time voice bot that integrates with WhatsApp Business API to handle voice calls using WebRTC technology. Users can call your WhatsApp Business number and have natural conversations with an AI-powered bot.

## Prerequisites

### WhatsApp Business API Setup

1. **Facebook Account**: Create an account at [facebook.com](https://facebook.com)
2. **Facebook Developer Account**: Create an account at [developers.facebook.com](https://developers.facebook.com)
3. **WhatsApp Business App**: Create a new [WhatsApp Business API application](https://developers.facebook.com/apps)
4. **Phone Number**: Add and verify a WhatsApp Business phone number
5. **Business Verification**: Complete business verification process (required for production only)
6. **Webhook Configuration**: Set up webhook endpoint for your application

> **Important Note**: For production, make sure your WhatsApp Business account has access to this feature.

> Find more details here:
>
> - [Getting Started Guide](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)
> - [Voice Calling Documentation](https://developers.facebook.com/docs/whatsapp/cloud-api/calling/)
> - [Webhooks Setup](https://developers.facebook.com/docs/whatsapp/webhooks/)

### WhatsApp Business API Configuration

#### Enable Voice Calls

Your WhatsApp Business phone number must be configured to accept voice calls[[2]](https://developers.facebook.com/docs/whatsapp/cloud-api/calling/):

> For development, you'll be provided with a free test phone number valid for 90 days.

1. Go to your WhatsApp Business API dashboard in Meta Developer Console
2. Navigate to **Configuration** → **Phone Numbers** → **Manage phone numbers**
3. Select your phone number
4. In the **Calls** tab, enable "Allow voice calls" capability
5. Save the configuration

#### Configure Webhook

Set up your webhook endpoint in the Meta Developer Console[[3]](https://developers.facebook.com/docs/whatsapp/webhooks/):

1. Go to **WhatsApp** → **Configuration** → **Webhooks**
2. Set callback URL: `https://your-domain.com/`
3. Set verify token: `your_webhook_verification_token`
   - This token should match your `WHATSAPP_WEBHOOK_VERIFICATION_TOKEN` environment variable
4. Click "Verify and save"
5. In the webhook fields below, select: `calls` (required for voice call events)

#### Configure Access Token

1. Go to **WhatsApp** → **API Setup**
2. Click "Generate access token"
   - Use this token for your `WHATSAPP_TOKEN` environment variable
3. Note your Phone Number ID - you'll need this for `PHONE_NUMBER_ID` configuration

## 🚀 Quick Start

### Environment Setup

1. **Install dependencies**:

   ```bash
   uv sync
   ```

2. **Configure environment variables**:
   ```bash
   cp env.example .env
   ```
   Edit `.env` file and add your API keys and configuration values.

### Run the Server

```bash
uv run server.py
```

> The server will start and listen for incoming WhatsApp webhook events.

### Connect Using WhatsApp

1. Find your WhatsApp test number in the Meta Developer Console
2. Call the number from your WhatsApp app
3. The bot should answer and engage in conversation

## Documentation References

- [WhatsApp Cloud API Getting Started](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)
- [Voice Calling API Documentation](https://developers.facebook.com/docs/whatsapp/cloud-api/calling/)
- [Webhook Configuration Guide](https://developers.facebook.com/docs/whatsapp/webhooks/)
- [SDP Overview and Samples](https://developers.facebook.com/docs/whatsapp/cloud-api/calling/reference#sdp-overview-and-sample-sdp-structures)

## 💡 Troubleshooting

- Ensure all dependencies are installed before running the server
- Verify your `.env` file contains all required configuration values
- Make sure voice calling is enabled for your WhatsApp Business number
- Check that your webhook URL is publicly accessible and properly configured
- Ensure your business account is verified for production use

## Notes

- Voice calling feature requires WhatsApp Business API access
- Test numbers are valid for 90 days in development mode
- Production deployment requires business verification
