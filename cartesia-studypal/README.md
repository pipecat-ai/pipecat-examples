# cartesia-studypal

## Have a conversation about any article on the web

`cartesia-studypal` is a fast conversational AI built using [Daily](https://www.daily.co/) or SmallWebRTC for real-time media transport, and [Cartesia](https://cartesia.ai) for speech-to-text and text-to-speech. Everything is orchestrated together (STT -> LLM -> TTS) using [Pipecat](https://www.pipecat.ai/).

## Supported Content Sources

`cartesia-studypal` can extract and discuss content from:

- **Wikipedia articles** - Any Wikipedia URL in any language

  - Example: `https://en.wikipedia.org/wiki/Artificial_intelligence`
  - Example: `https://es.wikipedia.org/wiki/Inteligencia_artificial`

- **arXiv papers** - Academic papers from arXiv.org
  - Example: `https://arxiv.org/abs/2312.00752` (Mamba: Linear-Time Sequence Modeling with Selective State Spaces)
  - Example: `https://arxiv.org/pdf/2312.00752` (PDF URLs also work)

**Note:** Content is automatically truncated to 10,000 tokens to fit within the LLM context window.

## Setup

1. Clone the repository
2. Copy `env.example` to a `.env` file and add API keys
3. Install the required packages: `uv sync`
4. Run from your command line:

   - Daily: `uv run bot.py -t daily`
   - SmallWebRTC: `uv run bot.py`

5. Connect using your browser by clicking on the link generated in the console
6. When prompted, enter a Wikipedia or arXiv URL you'd like to discuss

## Example Usage

```bash
$ uv run bot.py
Enter the URL of the article you would like to talk about: https://en.wikipedia.org/wiki/Python_(programming_language)
```

The bot will then be ready to answer questions and discuss the article content with you!
