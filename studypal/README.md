# studypal

### Have a conversation about any article on the web

studypal is a fast conversational AI built using [Daily](https://www.daily.co/) or SmallWebRTC for real-time media transport, [Deepgram](https://deepgram.com/) for speech-to-text, [OpenAI](https://openai.com/) for LLM inference, and [Cartesia](https://cartesia.ai) for text-to-speech. Everything is orchestrated together (VAD -> STT -> LLM -> TTS) using [Pipecat](https://www.pipecat.ai/).

## Setup

1. Clone the repository
2. Copy `env.example` to a `.env` file and add API keys
3. Install the required packages: `uv sync`
4. Run from your command line:

   - Daily: `uv run studypal.py -t daily`
   - SmallWebRTC: `uv run studypal.py`

5. Connect using your browser by clicking on the link generating in the console.
