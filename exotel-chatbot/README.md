# Exotel Chatbot

This project is a FastAPI-based chatbot that integrates with Exotel to handle WebSocket connections and provide real-time voice communication. The project includes endpoints for handling WebSocket voice streaming using Exotel's Voicebot Applet.

## Table of Contents

- [Exotel Chatbot](#exotel-chatbot)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Requirements](#requirements)
  - [Installation](#installation)
  - [Configure Exotel App Bazaar Application](#configure-exotel-app-bazaar-application)
  - [Running the Application](#running-the-application)
    - [Using Python (Option 1)](#using-python-option-1)
    - [Using Docker (Option 2)](#using-docker-option-2)
  - [Usage](#usage)

## Features

- **FastAPI**: A modern, fast (high-performance), web framework for building APIs with Python 3.6+.
- **WebSocket Support**: Real-time voice streaming using WebSockets.
- **CORS Middleware**: Allowing cross-origin requests for testing.
- **Exotel Integration**: Works with Exotel's Voicebot Applet for voice AI applications.
- **Custom Parameters**: Support for passing custom parameters from Exotel App Bazaar.
- **Dockerized**: Easily deployable using Docker.

## Requirements

- Python 3.10
- Docker (for containerized deployment)
- ngrok (for tunneling)
- Exotel Account with voice streaming enabled

## Installation

1. **Set up a virtual environment** (optional but recommended):

   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

2. **Install dependencies**:

   ```sh
   pip install -r requirements.txt
   ```

3. **Create .env**:
   Copy the example environment file and update with your settings:

   ```sh
   cp env.example .env
   ```

4. **Install ngrok**:
   Follow the instructions on the [ngrok website](https://ngrok.com/download) to download and install ngrok.

## Configure Exotel App Bazaar Application

1. **Start ngrok**:
   In a new terminal, start ngrok to tunnel the local server:

   ```sh
   ngrok http 8765
   ```

2. **Purchase a number**

   If you haven't already, purchase a number from Exotel.

   - Log in to the Exotel dashboard: https://my.exotel.com/
   - Navigate to ExoPhones and purchase a number
   - Note: You may need to complete KYC verification for your account

3. **Enable Voice Streaming (if not already enabled)**:

   Voice streaming may not be enabled by default on all accounts:

   - Contact Exotel support at `hello@exotel.com`
   - Request: "Enable Voicebot Applet for voice streaming for account [Your Account SID]"
   - Include your use case: "AI voice bot integration"

4. **Create Custom App in App Bazaar**:

   - Navigate to App Bazaar in your Exotel dashboard
   - Click "Create Custom App" or edit an existing app
   - Build your call flow:

     **Add Voicebot Applet**

     - Drag the "Voicebot" applet to your call flow
     - Configure the Voicebot Applet:
       - **URL**: `wss://your-ngrok-url.ngrok.io/ws`
       - **Custom Parameters** (optional): Add up to 3 parameters
         - Example: `serviceHost=customer-support.acme-corp`
         - Format: Add parameters directly to URL: `wss://your-ngrok-url.ngrok.io/ws?serviceHost=customer-support.acme-corp&botType=demo`
       - **Record**: Enable if you want call recordings

     **Optional: Add Hangup Applet**

     - Drag a "Hangup" applet at the end to properly terminate calls

   - Your final flow should look like:
     ```
     Call Start → [Voicebot Applet] → [Hangup Applet]
     ```

5. **Link Number to App**:

   - Navigate to "ExoPhones" in your dashboard
   - Find your purchased number
   - Click the edit/pencil icon
   - Under "App", select the custom app you just created
   - Save the configuration

   Now your number is ready to call.

6. **WebSocket URL Configuration**:

   Your Voicebot Applet should be configured with:

   - **URL**: `wss://abc123.ngrok.io/ws` (replace with your actual ngrok URL)
   - **Important**: Use `wss://` (secure WebSocket), not `https://`
   - **Custom Parameters**: Can be added to the URL as query parameters

## Running the Application

Choose one of these two methods to run the application:

### Using Python (Option 1)

**Run the FastAPI application**:

```sh
# Make sure you're in the project directory and your virtual environment is activated
python server.py
```

### Using Docker (Option 2)

1. **Build the Docker image**:

   ```sh
   docker build -t exotel-chatbot .
   ```

2. **Run the Docker container**:
   ```sh
   docker run -it --rm -p 8765:8765 exotel-chatbot
   ```

The server will start on port 8765. Keep this running while you test with Exotel.

## Usage

To start a call, simply make a call to your configured Exotel phone number. The Voicebot Applet will establish a WebSocket connection to your FastAPI application, which will handle the voice streaming accordingly.

### Expected WebSocket Message Flow

When a call is received, your server will get these messages:

1. **Connected Event**:

   ```json
   { "event": "connected" }
   ```

2. **Start Event** (with call data):

   ```json
   {
     "event": "start",
     "stream_sid": "95be037f0ff02b427c3a4a59ae72198c",
     "sequence_number": "1",
     "start": {
       "stream_sid": "95be037f0ff02b427c3a4a59ae72198c",
       "call_sid": "75b90b4b77ce9e6fe9a60a26f03d198c",
       "account_sid": "ezora2",
       "from": "+14129162450",
       "to": "08045680571",
       "custom_parameters": {
         "serviceHost": "customer-support.acme-corp"
       },
       "media_format": {
         "encoding": "base64",
         "sample_rate": "8000",
         "bit_rate": "128kbps"
       }
     }
   }
   ```

3. **Media Events**: Containing streaming audio data over the websocket connection.

### Key Differences from Other Providers

- **No XML configuration**: Exotel uses visual App Bazaar instead of XML files
- **8kHz audio format**: Fixed at 8kHz PCM, not configurable like other providers
- **Dashboard-based**: All configuration done through web interface
- **Custom parameters**: Limited to 3 parameters, max 256 characters total
- **Voicebot Applet**: Specific applet required for WebSocket streaming
