# Vonage Speech-to-Speech Bot (Pipecat)

A real-time voice chatbot using **Pipecat AI** with **Vonage Audio Connector** over **WebSocket**.
This example uses OpenAI Realtime for speech-in → speech-out (no separate STT/TTS services). The server exposes a WS endpoint (via **VonageAudioConnectorTransport**) that the Vonage **/connect API** connects to, bridging the live session into an OpenAI Realtime speech↔speech pipeline.


## Table of Contents

- [How It Works](#how-it-works)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Configuration](#environment-configuration)
- [Run your Server Application](#run-your-server-application)
- [Testing the Speech-to-Speech Bot](#testing-the-speech-to-speech-bot)

## How It Works

1. **Vonage connects to your Pipecat WebSocket server -** The /connect API creates a virtual participant and starts streaming audio frames.
2. **Parse the WebSocket messages -** Your Pipecat server reads incoming audio packets from Vonage and sets up a transport.
3. **Start the Pipecat pipeline -** Incoming audio is streamed directly into the OpenAI Realtime model which performs automatic speech recognition and real-time reasoning.
4. **The model generates speech responses -** Instead of returning text, the Realtime model produces synthesized audio frames as part of its speech-to-speech output stream.
5. **Return speech back to Vonage -** Pipecat sends audio frames back through the WebSocket, and Vonage injects them into the session in real time.

## Features

- **Real-time, bidirectional audio** using the WebSockets via Vonage Audio Connector
- **OpenAI Realtime powered pipeline** speech↔speech (no separate STT/TTS)
- **Silero VAD** for accurate speech-pause detection
- **Docker support** for simple deployment and isolation 

## Prerequisites

- A **Vonage(Opentok) account**
- An **OpenAI API Key**
- Python **3.10+**
- `uv` package manager
- **ngrok** (or any WS tunnel) for local testing
- Docker (optional)

## Setup

1. **Set up a virtual environment and install dependencies**:

    ```sh
    uv sync
    ```

2. **Create your .env file**:

    ```sh
    cp env.example .env
    ```
    Update .env with your credentials and session ID as mentioned in below Section.

## Environment Configuration

1. **Create an Opentok/Vonage Session and Publish a Stream**
    A Session ID is required for the Audio Connector.
    Note: You can use either Opentok or Vonage platform to create the session. Open the Playground (or your own app) to create a session and publish a stream.
    Copy the Session ID and set it in `.env` file:
    ```sh
    VONAGE_SESSION_ID=<paste-your-session-id-here>
    ```
    Always use **credentials from the same project** that created the `sessionId`.

2. **Set the Keys in `.env`**
    If the session was created using the OpenTok (API key + secret), set the following in your `.env`:

    ```sh
    # OpenAI Key (no quotes)
    OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxx

    # OpenTok credentials
    VONAGE_API_KEY=YOUR_API_KEY
    VONAGE_API_SECRET=YOUR_API_SECRET

    # Session ID created in Step 6
    VONAGE_SESSION_ID=1_MX4....

    # Leave blank; this is auto-filled after `/connect` API call
    VONAGE_CONNECTION_ID=...

    ```
   If the session was created using the Vonage platform (App ID + Private Key), set the following in your `.env`:

    ```sh
    # Vonage Platform API credentials
    VONAGE_APPLICATION_ID=YOUR_APPLICATION_ID
    VONAGE_PRIVATE_KEY=YOUR_PRIVATE_KEY_PATH

    # Session ID created in Step 6
    VONAGE_SESSION_ID=1_MX4....

    # Leave blank; auto-filled by client.py
    VONAGE_CONNECTION_ID=...

    ```

3. **Install ngrok**:

   Follow the instructions on the [ngrok website](https://ngrok.com/download) to download and install ngrok. You’ll use this to securely expose your local WebSocket server for testing.

4. **Start ngrok to expose the local WebSocket server**:

    **Run in a separate terminal**, start ngrok to tunnel the local server:

    ```sh
    ngrok http 8005
    ```

    You will see something like:

    ```sh
    Forwarding    https://a5db22f57efa.ngrok-free.app -> http://localhost:8005
    ```

    To form the **WSS** URL, replace https:// with wss://.

    Example like for above Forwarding URL below is the wss:// url:

    ```sh
    "websocket": {
        "uri": "wss://a5db22f57efa.ngrok-free.app",
        "audioRate": 16000,
        "bidirectional": true
    }
    ```

## Run your Server Application

You can run the server application using the command below:

    ```sh
    uv run server.py
    ```
    The server will start on port 8005 and wait for incoming Audio Connector connections.

## Testing the Speech-to-Speech Bot

1. Follow the instructions in: `examples/vonage-ac-s2s/client/README.md`.
2. Run the client program (`connect_and_stream.py`) to invoke the **/connect API**.
3. Once the connection is established, begin speaking in the Vonage Video session. Your audio will be forwarded through the Audio Connector to the Pipecat pipeline processed by OpenAI Realtime speech↔speech model and the synthesized response will be sent back into the session. 
4. You will hear the AI’s voice reply in real time, played back as audio from the virtual participant created by the `/connect` API.
