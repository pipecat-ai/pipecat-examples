# 🤖 Fully Local Voice AI Bot

A privacy-focused, real-time voice AI assistant that runs entirely on your local machine. Built with [Pipecat](https://github.com/pipecat-ai/pipecat) framework.


I walk through the entire setup in this 12-minute tutorial: 👉 https://youtu.be/URnVU5OyEQI

## ✨ Features

- 🔒 **Privacy First**: All processing happens locally - your conversations never leave your machine
- 🎤 **Real-time Voice**: Natural voice conversations with minimal latency
- 🧠 **Smart Turn-Taking**: Advanced Voice Activity Detection (VAD) for natural conversations
- 🌐 **WebRTC Streaming**: Browser-based interface, no app installation needed
- 📊 **Performance Metrics**: Built-in monitoring and usage tracking
- 🔧 **Highly Configurable**: Easy to swap components and adjust parameters

## 🏗️ Architecture

```
┌─────────────┐
│   Browser   │  ← User Interface
└──────┬──────┘
       │ WebRTC
┌──────▼──────────────────────────────────────────┐
│              Pipecat Pipeline                    │
│                                                  │
│  Audio In → VAD → Whisper STT → Context         │
│                      ↓                           │
│                  Ollama LLM                      │
│                      ↓                           │
│  Audio Out ← Piper TTS ← Context                │
└──────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

1. **Python 3.10+**
2. **Ollama** - Local LLM server
3. **Piper** - Local TTS server (optional, can use cloud TTS)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/local-voice-ai-bot.git
   cd local-voice-ai-bot
   ```

2. **Install dependencies**
   ```bash
   # Using uv (recommended)
   uv pip install "pipecat-ai[whisper,ollama,piper]"
   
   # Or using pip
   pip install "pipecat-ai[whisper,ollama,piper]"
   ```

3. **Install and start Ollama**
   ```bash
   # Install from https://ollama.ai
   
   # Pull a model (choose one)
   ollama pull llama3.2:1b    # Fastest, 1GB
   ollama pull llama3:latest  # Balanced, 8GB
   
   # Start Ollama server
   ollama serve
   ```

4. **Install and start Piper TTS** (Optional)
   ```bash
   # Install from https://github.com/rhasspy/piper
   
   # Start Piper server
   python piper_server.py --port 5002
   ```
   
   *Note: You can also use cloud TTS (Cartesia) by setting `CARTESIA_API_KEY` in `.env`*

### Running the Bot

1. **Create .env file** (optional, for cloud services)
   ```bash
   # Only needed if using cloud alternatives
   CARTESIA_API_KEY=your_key_here
   PIPER_BASE_URL=http://127.0.0.1:5002/api/tts
   ```

2. **Start the bot**
   ```bash
   uv run bot_local.py
   ```

3. **Open in browser**
   ```
   http://localhost:7860/client
   ```

4. **Start talking!** 🎉

## 🔧 Configuration

### Whisper Model Selection

Edit `bot_local.py` to change the STT model:

```python
stt = WhisperSTTService(
    model=Model.TINY,  # Options: TINY, BASE, SMALL, MEDIUM, LARGE
    device='auto'
)
```

| Model | Size | Speed | Accuracy | RAM Required |
|-------|------|-------|----------|--------------|
| TINY | 75MB | ⚡⚡⚡ | ⭐⭐ | ~1GB |
| BASE | 145MB | ⚡⚡ | ⭐⭐⭐ | ~2GB |
| SMALL | 500MB | ⚡ | ⭐⭐⭐⭐ | ~3GB |
| MEDIUM | 1.5GB | 🐌 | ⭐⭐⭐⭐⭐ | ~5GB |
| LARGE | 3GB | 🐌🐌 | ⭐⭐⭐⭐⭐⭐ | ~10GB |

### Ollama Model Selection

```python
llm = OLLamaLLMService(
    model="llama3.2:1b",  # Change to your preferred model
    base_url="http://localhost:11434/v1"
)
```

Available models (install with `ollama pull <model>`):
- `llama3.2:1b` - Fast, good for testing (1GB)
- `llama3:latest` - Balanced performance (8GB)
- `mistral` - Alternative option (7GB)
- `codellama` - Code-focused (7GB)

### Voice Activity Detection (VAD)

Adjust speech detection sensitivity:

```python
VADParams(
    stop_secs=0.2,  # Silence duration to end speech (default: 0.2s)
    confidence=0.7,  # Detection confidence threshold
    min_volume=0.6   # Minimum audio volume
)
```

## 🌐 Cloud Alternatives

Want to use cloud services? Uncomment these sections in `bot_local.py`:

### Cloud STT (Deepgram)
```python
stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
```

### Cloud LLM (OpenAI)
```python
llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))
```

### Cloud TTS (Cartesia)
```python
tts = CartesiaTTSService(
    api_key=os.getenv("CARTESIA_API_KEY"),
    voice_id="71a7ad14-091c-4e8e-a314-022ece01c121"
)
```

## 📋 Command-Line Options

```bash
# Default (WebRTC on port 7860)
uv run bot_local.py

# Custom port
uv run bot_local.py --port 8080

# Use Daily.co transport
uv run bot_local.py --transport daily

# Enable verbose logging
uv run bot_local.py -v
```

## 🐛 Troubleshooting

### Whisper Model Not Loading
```bash
# Ensure you have the whisper extras installed
uv pip install "pipecat-ai[whisper]"
```

### Ollama Not Responding
```bash
# Check if Ollama is running
curl http://localhost:11434/api/version

# Restart Ollama
ollama serve
```

### Piper TTS Not Working
```bash
# Test Piper server
curl http://127.0.0.1:5002/api/tts

# Use cloud TTS as fallback (set CARTESIA_API_KEY in .env)
```

### Audio Issues
- **No microphone input**: Check browser permissions
- **No audio output**: Verify speaker settings
- **Choppy audio**: Try a smaller Whisper model (TINY or BASE)

## 📊 Performance Tips

1. **Use GPU acceleration**: Whisper and Ollama support CUDA/Metal
   ```python
   stt = WhisperSTTService(model=Model.BASE, device='cuda')  # For NVIDIA GPUs
   ```

2. **Choose smaller models**: Start with `TINY` Whisper and `llama3.2:1b` Ollama

3. **Adjust VAD parameters**: Increase `stop_secs` for slower responses but better accuracy

4. **Monitor metrics**: Check logs for processing times and bottlenecks

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the BSD 2-Clause License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Pipecat](https://github.com/pipecat-ai/pipecat) - Voice AI framework
- [Whisper](https://github.com/openai/whisper) - Speech-to-text
- [Ollama](https://ollama.ai) - Local LLM runtime
- [Piper](https://github.com/rhasspy/piper) - Text-to-speech

## 🔗 Links

- [Documentation](https://docs.pipecat.ai)
- [Pipecat GitHub](https://github.com/pipecat-ai/pipecat)
- [Report Issues](https://github.com/yourusername/local-voice-ai-bot/issues)

---

Made with ❤️ for privacy-conscious AI enthusiasts