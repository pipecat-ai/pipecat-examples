# Pipecat Examples - AI Coding Agent Instructions

This repository contains example applications for [Pipecat](https://github.com/pipecat-ai/pipecat), an open-source framework for building voice and multimodal AI applications.

**Always consult [docs.pipecat.ai](https://docs.pipecat.ai/) for API references, guides, and troubleshooting.**

**Always consult [docs.daily.co](https://docs.daily.co/reference/rest-api) for Daily.co transport details.**

## Core Concept: Frames and Frame Processing

Pipecat's fundamental pattern is **pushing and processing frames**. When creating examples, always follow this pattern:

- **Frames** are data containers (audio, text, images, control signals) that flow through your pipeline like packages on a conveyor belt
- **Frame Processors** receive frames, process them, and push new frames downstream via `push_frame()`
- Processors don't consume frames—they pass them along, allowing multiple processors to use the same data
- Frame order is guaranteed: SystemFrames process immediately, DataFrames/ControlFrames are queued in order

Every custom processor follows this pattern:
```python
class MyProcessor(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        # Handle specific frame types
        if isinstance(frame, SomeFrame):
            # Do processing...
        # Always push frame to next processor
        await self.push_frame(frame, direction)
```

**Reference:** [Pipeline & Frame Processing Guide](https://docs.pipecat.ai/guides/learn/pipeline)

## Architecture Overview

Each example is a **standalone project** in its own directory with:
- Independent `pyproject.toml` and dependencies (managed via `uv`)
- Own `env.example` file for required API keys
- Local README.md with setup instructions

**Common pipeline pattern** (see [runner-examples/01-single-transport-bot.py](runner-examples/01-single-transport-bot.py)):
```
transport.input() → STT → context_aggregator.user() → LLM → TTS → transport.output() → context_aggregator.assistant()
```

## Development Workflow

```bash
# Per-example setup (from example's directory)
uv sync
cp env.example .env  # Add API keys

# Run bot (varies by example)
uv run bot.py
# or with transport flag
uv run bot.py --transport daily

# Linting (from repo root)
./scripts/fix-ruff.sh     # Auto-fix formatting & imports
./scripts/pre-commit.sh   # Check before committing
```

## Key Patterns

### Bot Entry Point
Bots use `async def run_bot(transport: BaseTransport)` signature to work with any transport:
```python
async def run_bot(transport: BaseTransport):
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY",""))
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY", ""))
    tts = CartesiaTTSService(api_key=os.getenv("CARTESIA_API_KEY", ""))
    
    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(context)
    
    pipeline = Pipeline([transport.input(), stt, context_aggregator.user(), llm, tts, transport.output(), context_aggregator.assistant()])
    task = PipelineTask(pipeline, params=PipelineParams(...))
    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
```

### Transport Types
- **Daily**: WebRTC via Daily.co (`DailyTransport`, `DailyParams`)
- **WebRTC**: Direct peer-to-peer (`SmallWebRTCTransport`, `TransportParams`)
- **WebSocket/Telephony**: Twilio, Telnyx, Plivo (`FastAPIWebsocketTransport`, `TwilioFrameSerializer`)

### Event Handlers
Use transport decorators for lifecycle events:
```python
@transport.event_handler("on_client_connected")
async def on_client_connected(transport, client):
    await task.queue_frames([LLMRunFrame()])
```

## File Conventions

- **License header**: All Python files start with BSD 2-Clause copyright block
- **Imports**: Use `ruff` for sorting (line-length: 100, select: ["I"])
- **Environment**: Always `load_dotenv(override=True)` at module level
- **API keys**: Access via `os.getenv("KEY_NAME")`, never hardcode

## Common Services

| Service | Import | Common Voice IDs |
|---------|--------|------------------|
| Deepgram STT | `pipecat.services.deepgram.stt` | N/A |
| Cartesia TTS | `pipecat.services.cartesia.tts` | `71a7ad14-...` (British Reading Lady) |
| ElevenLabs TTS | `pipecat.services.elevenlabs.tts` | `pNInz6ob...` |
| OpenAI LLM | `pipecat.services.openai.llm` | N/A |
| Google LLM | `pipecat.services.google.llm` | N/A |

## Example Categories

- `simple-chatbot/`, `twilio-chatbot/`: Client/server reference implementations
- `phone-chatbot/`: Daily PSTN/SIP telephony examples
- `runner-examples/`: Transport abstraction patterns
- `deployment/`: Production deployment (Fly.io, Modal, Pipecat Cloud)
