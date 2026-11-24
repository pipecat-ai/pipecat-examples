# Client-side function calling

A voice bot whose LLM calls tools that run in the browser, not on the server.
The client registers handlers with
[`registerFunctionCallHandler`](https://docs.pipecat.ai/api-reference/client/js/client-methods#registerfunctioncallhandler),
runs them when the LLM calls them, and sends the result back to the bot.

The two tools need something only the browser has:

- `get_local_time`: the user's local date, time and timezone.
- `set_background_color`: changes the page's background color.

Try saying _"What time is it?"_ or _"Make the background light blue."_

## How it works

```
LLM calls get_local_time
   │  server handler returns without calling result_callback → call stays in progress
   ▼
RTVIObserver ──── llm-function-call-in-progress {function_name, tool_call_id, arguments} ───▶ client
                                                                                             │ runs the handler
RTVIProcessor ◀──────────── llm-function-call-result {tool_call_id, result} ─────────────────┘
   │  pushes FunctionCallResultFrame
   ▼
assistant aggregator adds the result to the context and runs the LLM again
```

The server needs three things (see `server/bot.py`):

1. **Declare each tool as a direct function** in the `LLMContext`. Pipecat
   builds its schema from the signature and docstring and registers it with
   the LLM.
2. **Leave `params.result_callback` uncalled** in the function body. The call
   then stays open until the client's result arrives.

   ```python
   async def get_local_time(params: FunctionCallParams):
       """Get the current local date, time and timezone from the user's device."""

   context = LLMContext(tools=[get_local_time])
   ```

3. **Report the call's name and arguments to the client.** The client picks
   its handler by function name, and the default report level (`none`) sends
   neither. Set `function_call_report_level` to `ARGUMENTS` (or `FULL`) for
   these tools:

   ```python
   rtvi_observer_params=RTVIObserverParams(
       function_call_report_level={
           "*": RTVIFunctionCallReportLevel.NONE,
           "get_local_time": RTVIFunctionCallReportLevel.ARGUMENTS,
       },
   )
   ```

The client registers one handler per tool and returns the result (see
`client/javascript/src/app.js`):

```js
pcClient.registerFunctionCallHandler("get_local_time", async ({ arguments: args }) => {
  return { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone };
});
```

A handler that returns `undefined` sends nothing back, so always return a
result, even one that reports an error. The bot waits on a call until its result
arrives: `timeout_secs` doesn't apply, because the server function has already
returned.

## Quick start

### 1. Start the bot server

```bash
cd server
uv sync
cp env.example .env   # add your API keys
uv run bot.py -t daily
```

This starts the Pipecat runner on `http://localhost:7860`, which exposes the
`/start` endpoint the client calls.

### 2. Start the client

Requires Node >= 22.14.0 (`nvm use` picks it up from `.nvmrc`).

```bash
cd client/javascript
npm install
npm run dev
```

Open http://localhost:5173 and click **Connect**. Tool calls and their results
appear in the log.

## Requirements

- Python 3.11+
- Node.js 22.14+
- Daily, Deepgram, OpenAI and Cartesia API keys
