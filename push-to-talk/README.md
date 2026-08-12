# Push-to-Talk Voice AI Agent

A voice AI agent with push-to-talk functionality. Users hold a button to speak, and release it to send their message to the AI.

## How it Works

- **Client**: Hold the "Hold to Talk" button to speak, release to send
- **Server**: The user aggregator uses `ExternalUserTurnStrategies`, so it only collects transcription between the button press and release. Audio still flows to STT the whole time; transcripts that arrive outside a held turn are simply ignored.
- **Real-time**: Uses WebRTC for low-latency audio communication

## Quick Start

To run this demo, you'll need two terminal windows.

### Terminal 1: Server Setup

1. Create virtual environment and install dependencies:

```bash
uv sync
```

2. Configure environment:

```bash
cp env.example .env
```

Edit `.env` and add your API keys:

- `CARTESIA_API_KEY`: For text-to-speech
- `OPENAI_API_KEY`: For the LLM
- `DEEPGRAM_API_KEY`: For speech-to-text
- `DAILY_API_KEY`: For WebRTC transport

3. Run the server:

```bash
uv run bot.py -t daily
```

### Terminal 2: Client Setup

1. Install dependencies:

```bash
npm i
```

2. Configure environment:

```bash
cp env.example .env.local
```

3. Start the client:

```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000)

## Usage

1. Click "Connect" to join the session
2. Hold "Hold to Talk" button and speak
3. Release the button to send your message
4. The AI will respond with audio
5. Click "Disconnect" to end the session

## Architecture

The push-to-talk functionality is encapsulated in custom [user turn strategies](https://docs.pipecat.ai/api-reference/server/utilities/turn-management/user-turn-strategies) (see `PushToTalkUserTurnStrategies` in `server/bot.py`). The user aggregator is configured with these strategies, making the client button the sole authority over when a user turn starts and stops:

- Client sends `{type: "push_to_talk", data: {state: "start"}}` when the button is pressed.
- `PushToTalkUserTurnStartStrategy` sees the message and starts the user turn. Because interruptions are enabled, this also barges in on the bot if it's speaking. The aggregator begins collecting transcription.
- Client sends `{type: "push_to_talk", data: {state: "stop"}}` when the button is released.
- `PushToTalkUserTurnStopStrategy` ends the turn. It extends `ExternalUserTurnStopStrategy`, so it waits briefly for the trailing transcript, then pushes the aggregated message to the LLM.

The strategies react to the `push_to_talk` message directly, so no separate frame-handling processor is needed. (For an app that mixes push-to-talk with live VAD-driven turns, you'd instead translate the message into custom frames in an `on_client_message` handler — see [pipecat-ai/ptt-and-conversation](https://github.com/kwindla/ptt-and-conversation).)

## Client-side Tool Calling

This example also shows how to run an LLM tool call **in the browser** instead of on the server. Reach for this when the tool needs something only the client has: the DOM, geolocation, a local file, or a logged-in session. Here the tool is `get_browser_info`. Ask the bot "what browser am I using?" and it reads back your real user agent, screen size, language, and time zone, none of which the server ever saw.

### How it works

1. The server advertises the tool to the LLM in `LLMContext(tools=...)` and registers `run_on_client` as its handler.
2. The LLM calls the tool. Pipecat tells the client the call is in progress via the `llm-function-call-in-progress` RTVI message.
3. `run_on_client` returns **without** calling `params.result_callback`. That leaves the call open instead of answering it.
4. The client's registered handler runs and returns a value, which the client sends back as `llm-function-call-result`.
5. Pipecat turns that message into the function call's result, adds it to the LLM context, and runs the LLM again so the bot can talk about it.

The two halves are `run_on_client` plus the `CLIENT_TOOL` wiring in `server/bot.py`, and `client/src/app/hooks/useClientTools.ts`. To add another client-run tool you need four things: a `FunctionSchema`, a `register_function` call, a report-level entry, and a matching `registerFunctionCallHandler` in the hook.

### Things that will bite you

Every one of these fails silently, so they are worth knowing up front.

- **Set the report level.** `function_call_report_level` defaults to `NONE`, which sends only a `tool_call_id`. The client cannot dispatch a call it cannot name, so client-run tools must opt in to `FULL`.
- **Return something non-empty.** An empty result (`null`, `{}`, `""`) is treated as "nothing to say" and the bot will not speak a follow-up.
- **There is no timeout.** If the client never answers, the call stays open for the rest of the session and the bot just stops. Handle your own errors and always return a value.
- **Interruption does not cancel these calls.** Once the server handler returns, Pipecat has nothing left to cancel. Press the talk button while a tool call is in flight and the result still lands in the context afterwards.
- **Parallel calls are grouped.** If you add more client tools and the LLM calls several at once, one unanswered call blocks the whole group.
- **Client SDK support.** This flow needs `@pipecat-ai/client-js` 1.6.0 or newer. Older web clients, and the current iOS and Android SDKs, only understand the deprecated `llm-function-call` message.

## Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) to deploy your bot to Pipecat Cloud.
