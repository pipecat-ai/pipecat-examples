# Python Client for Server Testing

This Python client allows you to test the **Vonage Pipecat WebSocket server** by calling the Vonage **/connect** API. It creates a virtual Audio Connector participant inside your Vonage Video session, streams audio from the session to your Pipecat pipeline and plays back the generated response in real time.

## Setup Instructions

1. **Open the client directory in separate terminal**
    You do **not** need to clone the repository again.
    If you already cloned it for the server setup, simply open a new terminal and navigate to:
    ```sh
    cd vonage-pipecat/examples/vonage-ac-s2s/client
    ```

2. **Install dependencies**:
    ```sh
    uv sync
    ```

3. **Create .env**:

    ```sh
    cp env.example .env
    ```

4. **Use the existing Vonage/Opentok Session from the server setup**
    During the server setup, you already:
    1. Created a Vonage/Opentok Video Session
    2. Published a stream
    3. Verified audio is flowing inside the session
    The client does **not** need a new session.
    The `/connect` API will attach to this existing session.
    Simply copy the Session ID you used earlier into your `.env` file:
    ```sh
    VONAGE_SESSION_ID=<paste-your-session-id-here>
    ```

    If you are using Opentok platform, set OPENTOK_API_URL in your .env:
    ```sh
    OPENTOK_API_URL=https://api.opentok.com
    ```
   If you are using Vonage platform, set VONAGE_API_URL in your .env:
    ```sh
    VONAGE_API_URL=api.vonage.com
    ```

    **Note:** Ensure you use the **credentials** from the **same project** that created this session. 

5. **Configure credentials and WebSocket settings in `.env`**
    If you created the session in Opentok platform, set the following in your `.env`:
    ```sh
    # OpenTok credentials
    VONAGE_API_KEY=YOUR_API_KEY
    VONAGE_API_SECRET=YOUR_API_SECRET

    # WebSocket URL of your Pipecat server (ngrok or production)
    WS_URI=wss://<your-ngrok-domain>

    # Session ID from Step 5
    VONAGE_SESSION_ID=1_MX4....

    # API base
    OPENTOK_API_URL=https://api.opentok.com

    # Leave blank — this is auto-filled after `/connect` API call
    VONAGE_CONNECTION_ID=

    # Keep rest as same.
    ```
   If you created the session in Vonage platform, set the following in your `.env`:

    ```sh
    # Vonage SDK credentials
    VONAGE_APPLICATION_ID=YOUR_APPLICATION_ID
    VONAGE_PRIVATE_KEY=YOUR_PRIVATE_KEY_PATH

    # Websocket URL of your Pipecat Server (ngrok or production)
    WS_URI=wss://<your-ngrok-domain>

    # Session ID from Step 5
    VONAGE_SESSION_ID=1_MX4....

    # API base
    VONAGE_API_URL=api.vonage.com

    # Leave blank — this is auto-filled after `/connect` API call
    VONAGE_CONNECTION_ID=

    # Keep rest as same.
    ```

6. **Ensure your Pipecat WebSocket Server is running**:
    Before running the client, ensure Websocket Server is running. The client cannot connect unless the WebSocket endpoint is reachable.

7. **Run the Client**:
    The client triggers the `/connect` API → Vonage creates an Audio Connector → audio begins flowing.
    If using the Opentok API Key + Secret, run:
    ```sh
    uv run connect_and_stream.py
    ```

    If using Vonage Application ID + Private Key, run:
    ```sh
    uv run connect_and_stream_vonage.py
    ```
    When successful:
    1) `VONAGE_CONNECTION_ID` is automatically added to `.env`.
    2) The caller's audio is streamed into Pipecat
    3) The AI-generated speech response is injected back into the session

**Overriding `.env` Values (Optional)**
The script reads everything from .env via os.getenv().
You can still override via flags if you want, e.g.:

    ```sh
    # Example
    uv run connect_and_stream.py --ws-uri wss://my-ngrok/ws --audio-rate 16000

    # OR
    uv run connect_and_stream_vonage.py --ws-uri wss://my-ngrok/ws --audio-rate 16000
    ```
