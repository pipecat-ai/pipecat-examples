# Web Client

Basic implementation using the [Pipecat JavaScript SDK](https://docs.pipecat.ai/client/js/introduction)
with Daily transport configured for faster-than-realtime audio playback.

## Setup

1. Run the server-side bot; see the [main README](../README.md).

2. Navigate to the `client` directory:

   ```bash
   cd client
   ```

3. Install dependencies:

   ```bash
   yarn install
   ```

4. Copy the env file and configure it:

   ```bash
   cp env.example .env
   ```

5. Run the client app:

   ```bash
   yarn dev
   ```

6. Visit http://localhost:5173 in your browser.
