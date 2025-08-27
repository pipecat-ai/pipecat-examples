# WhatsApp WebRTC Bot

A real-time voice bot that integrates with WhatsApp Business API to handle voice calls using WebRTC technology. Users can call your WhatsApp Business number and have natural conversations with an AI-powered bot.

## Features

- **Real-time Voice Communication**: Handle WhatsApp incoming voice calls with low-latency audio streaming
- **WebRTC Integration**: Seamless peer-to-peer audio connection with WhatsApp users
- **Webhook Processing**: Automatic handling of WhatsApp Business API webhooks
- **Background Bot Management**: Concurrent handling of multiple simultaneous calls
- **Graceful Shutdown**: Proper cleanup of resources and active connections

## Prerequisites

### WhatsApp Business API Setup

1. **Facebook Account**: Create an account at [facebook.com](https://facebook.com)
2. **Facebook Developer Account**: Create an account at [developers.facebook.com](https://developers.facebook.com)
3. **WhatsApp Business App**: Create a new [WhatsApp Business API application](https://developers.facebook.com/apps)
4. **Phone Number**: Add and verify a WhatsApp Business phone number
5. **Webhook Configuration**: Set up webhook endpoint for your application

> You can find more details here:
> - https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/
> - https://developers.facebook.com/docs/whatsapp/cloud-api/calling/user-initiated-calls
> - https://developers.facebook.com/docs/whatsapp/cloud-api/calling/call-settings

### WhatsApp Business API Configuration

#### Enable Voice Calls
Your WhatsApp Business phone number must be configured to accept voice calls:

> When creating you app for development, you will be provided with a free phone number which you can use to test for 90 days.

1. Go to your WhatsApp Business API dashboard
2. Navigate to Configuration -> Phone Numbers → Manage phone numbers
3. Select your phone number
3. Inside the "Calls" tab click to "Allow voice calls" capability
4. Save the configuration

#### Configure Webhook
Set up your webhook endpoint in the Meta Developer Console:

1. Go to WhatsApp → Configuration
2. Set callback URL: `https://your-domain.com/`
3. Set verify token: `your_webhook_verification_token`
   - This is the same token which you will use inside WHATSAPP_WEBHOOK_VERIFICATION_TOKEN
4. Press to "verify and save"
4. Below in the webhook fields, you will need to select: `calls`

#### Configure access token
1. Go to WhatsApp → API Setup
2. Click to Generate access token
   - - This is the same token which you will use inside WHATSAPP_TOKEN
3. Look at you Phone number id, you will need this to configure inside PHONE_NUMBER_ID


## 🚀 Quick Start

### Start the Bot Server

#### Set Up the Environment
1. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   - Copy `env.example` to `.env`
   ```bash
   cp env.example .env
   ```
   - Add your API keys

#### Run the Server
```bash
python server.py
```

### Connect Using WhatsApp

You must find your test whatsapp number, and press to call.

## References
- https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/
- https://developers.facebook.com/docs/whatsapp/cloud-api/calling/user-initiated-calls
- https://developers.facebook.com/docs/whatsapp/cloud-api/calling/reference#sdp-overview-and-sample-sdp-structures

### 💡 Notes
- Ensure all dependencies are installed before running the server.
- Check the `.env` file for missing configurations.
- Need to enable to accept the "call" in the test phone number
