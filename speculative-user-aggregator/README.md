# speculative-user-aggregator

`speculative-user-aggregator` is a fast conversational AI built using [Daily](https://www.daily.co/) or SmallWebRTC for real-time media transport, [Cartesia](https://cartesia.ai) for speech-to-text, [OpenAI](https://openai.com/) for LLM inference, and [Cartesia](https://cartesia.ai) for text-to-speech. Everything is orchestrated together (VAD -> STT -> LLM -> TTS) using [Pipecat](https://www.pipecat.ai/).

## Speculating

This example defines a `SpeculativeUserAggregator` class, alongside `TurnEagerEndFrame` and `TurnResumeFrame`, to generate a "speculative" agent response slightly earlier than normal. This can result in slightly quicker agent responses, on the order of half a second, compared to the standard `LLMUserAggregator`.

Speculation is triggered by `on_turn_eager_end` and canceled by `on_turn_resume` from `CartesiaTurnsSTTService`:

1. `on_turn_eager_end` -> `TurnEagerEndFrame` -> adds a speculative `LLMContextFrame`
2. `on_turn_resume` -> `TurnResumeFrame` -> `InterruptionFrame` and removes the speculative `LLMContextFrame`

## Setup

1. Clone the repository
2. Copy `env.example` to a `.env` file and add API keys
3. Install the required packages: `uv sync`
4. Run from your command line:
   - Daily: `uv run bot.py -t daily`
   - SmallWebRTC: `uv run bot.py`

5. Connect using your browser by clicking on the link generated in the console
