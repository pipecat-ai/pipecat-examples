# 🤖 Pipecat Multi-LLM Fallback Example with Runtime Error Recovery

**Author:** Abdul Matin  
**Company:** PlayOwnAI  
📧 **Email:** playownai@gmail.com  
🔗 **GitHub:** [matinict](https://github.com/matinict)

---

## 📘 Overview

This example demonstrates a **robust multi-LLM fallback mechanism** built using **[Pipecat](https://github.com/pipecat-ai/pipecat)**.  
It automatically recovers from runtime errors and switches between available Large Language Models (LLMs) — ensuring your AI assistant always stays responsive.

The bot listens to **voice input** and replies **naturally**, using either local or cloud models depending on availability.

### 📺 Demo Video
[PlayOwnAI on YouTube](https://www.youtube.com/@PlayOwnAi/)

---

## ⚙️ How It Works

The bot uses an intelligent **fallback chain**:

1️⃣ **Ollama (Local)** - Fastest, free, and privacy-friendly  
2️⃣ **Google Gemini** - Cloud backup (via API key)  
3️⃣ **OpenAI GPT** - Ultimate fallback (via API key)  
4️⃣ **Graceful Exit** - Helpful error messages if all fail

**Runtime Recovery:** If the selected LLM fails during conversation, the system logs errors and suggests alternatives.

---

## 🧩 Required AI Services

| Service | Purpose | Type | Status |
|---------|---------|------|--------|
| **Deepgram** | Speech-to-Text (STT) | Required | Recommended |
| **Cartesia** | Text-to-Speech (TTS) | Optional | Recommended |
| **Ollama** | Local LLM | Optional | Primary choice |
| **Google Gemini** | Cloud LLM Fallback | Optional | Secondary choice |
| **OpenAI** | Cloud LLM Fallback | Optional | Tertiary choice |

---

## 📦 Installation

### Option 1: Using `uv` (Recommended)

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone or navigate to your project
cd /var/POAi/pipecat-quickstart

# Create virtual environment and sync dependencies
uv sync

# Or manually add dependencies:
uv add pipecat-ai loguru python-dotenv httpx \
       deepgram-sdk cartesia openai google-generativeai \
       torch torchaudio numpy fastapi uvicorn pydantic
```

### Option 2: Using `pip`

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🔧 Configuration

### Step 1: Create `.env` File

```bash
cd /var/POAi/pipecat-quickstart
cat > .env << 'EOF'
# ===== DEEPGRAM (Speech-to-Text) =====
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# ===== CARTESIA (Text-to-Speech) =====
CARTESIA_API_KEY=your_cartesia_api_key_here

# ===== OLLAMA (Local LLM) =====
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:latest

# ===== GOOGLE GEMINI (Cloud Fallback 1) =====
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash-exp

# ===== OPENAI (Cloud Fallback 2) =====
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
EOF
```

### Step 2: Get API Keys

**Google Gemini:**
- Visit: https://aistudio.google.com/app/apikeys
- Generate API key
- Add to `.env`

**OpenAI:**
- Visit: https://platform.openai.com/api-keys
- Create new secret key
- Add to `.env`

**Deepgram:**
- Visit: https://console.deepgram.com
- Create account & generate API key
- Add to `.env`

**Cartesia:**
- Visit: https://www.cartesia.ai
- Create account & generate API key
- Add to `.env`

---

## 🚀 Running the Bot

### Step 1: Start Ollama (if using local LLM)

```bash
# Terminal 1: Start Ollama service
ollama serve

# In another terminal, pull the model (first time only)
ollama pull qwen2.5:latest
```

### Step 2: Verify Ollama Setup

```bash
# Check installed models
ollama list

# Test Ollama API
curl http://localhost:11434/api/tags

# Test a model
ollama run qwen2.5:latest "Hello"
```

### Step 3: Run Debug Script (Optional)

```bash
# Test your Ollama connection before running the bot
uv run python test_ollama_debug.py
```

Expected output:
```
✅ Ollama is running
📋 Available models (5):
   • qwen2.5:latest (4.7 GB)
   • ...
✅ ALL TESTS PASSED - Ollama is ready!
```

### Step 4: Start the Bot

```bash
# Terminal 2: Run the bot
uv run botLLMFB.py

# Or with pip:
python botLLMFB.py
```

Expected output:
```
🚀 Starting Pipecat bot...
🔹 Trying Ollama local model...
Testing Ollama model: qwen2.5:latest...
✅ Using local Ollama model (qwen2.5:latest)
🤖 Selected LLM: ollama
🎧 Starting bot pipeline...

🚀 Bot ready!
   → Open http://localhost:7860/client in your browser
```

### Step 5: Open in Browser

Open your browser and navigate to:
```
http://localhost:7860/client
```

---

## ✅ Verification Checklist

Before running the bot, verify:

- [ ] **Ollama installed:** `ollama --version`
- [ ] **Model available:** `ollama list` (should show `qwen2.5:latest`)
- [ ] **`.env` file created** with all required API keys
- [ ] **Dependencies installed:** `uv sync` or `pip install -r requirements.txt`
- [ ] **Ollama running:** `curl http://localhost:11434/api/tags` (returns 200)
- [ ] **Deepgram API key set** in `.env`

---

## 🔍 Debugging & Troubleshooting

### Test Ollama Connection

```bash
uv run python test_ollama_debug.py
```

### View Real-Time Logs

The bot uses `loguru` for detailed logging. Check output for:
- LLM selection attempts
- API connection status
- Audio processing events
- Error messages with suggestions

### Common Issues & Solutions

**Issue: "Ollama returned status 404"**
```
✗ Solution: Make sure OLLAMA_URL in .env is http://localhost:11434 (without /v1)
```

**Issue: "Model not found"**
```bash
# Pull the model
ollama pull qwen2.5:latest
```

**Issue: "Cannot connect to Ollama"**
```bash
# Ensure Ollama is running
ollama serve
```

**Issue: "GEMINI_API_KEY not found"**
```
✗ Add to .env: GEMINI_API_KEY=your_actual_key_here
```

**Issue: "Bot switches to Gemini instead of using Ollama"**
```bash
# Run debug script to see what's happening
uv run python test_ollama_debug.py

# Make sure model exists:
ollama list
```

---

## 📁 Project Structure

```
pipecat-quickstart/
├── botLLMFB.py              # Main bot with fallback logic
├── test_ollama_debug.py     # Debug script for Ollama connection
├── requirements.txt         # Python dependencies
├── .env                     # API keys (keep secret!)
├── .env.example             # Template for .env file
└── README.md                # This file
```

---

## 🎯 Features

✨ **Multi-LLM Support** - Ollama, Google Gemini, OpenAI  
✨ **Automatic Fallback** - Switches to next LLM if one fails  
✨ **Voice I/O** - Listen and respond naturally  
✨ **Local Privacy** - Ollama runs locally without data leaving your machine  
✨ **Cloud Backup** - Gemini/OpenAI when local isn't available  
✨ **Error Recovery** - Graceful handling of all failures  
✨ **Real-Time Logging** - See exactly what the bot is doing  

---

## 📊 LLM Comparison

| Feature | Ollama | Gemini | OpenAI |
|---------|--------|--------|--------|
| Cost | Free | Paid (API) | Paid (API) |
| Privacy | Local ✅ | Cloud | Cloud |
| Speed | Fast | Medium | Medium |
| Offline | Yes ✅ | No | No |
| Quality | Good | Excellent | Excellent |
| Setup | Easy | Medium | Medium |

---

## 🌐 Connect with Us

Follow PlayOwnAI for more AI projects:

[![Facebook](https://img.shields.io/badge/Follow-Facebook-1877F2?logo=facebook&logoColor=white)](https://web.facebook.com/Playownai/)
[![LinkedIn](https://img.shields.io/badge/Follow-LinkedIn-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/company/playownai)
[![YouTube](https://img.shields.io/badge/Subscribe-@PlayOwnAi-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/@PlayOwnAi/)

---

## 📝 Notes

- **First run** may take 20 seconds to load models (normal)
- **Keep Ollama running** in background: `ollama serve`
- **All voice processing** happens locally through Pipecat
- **STT** (speech-to-text) uses Deepgram
- **TTS** (text-to-speech) uses Cartesia
- **LLM selection** is automatic based on availability

---

## 🆘 Getting Help

1. **Check logs:** Look for error messages in console output
2. **Run debug script:** `uv run python test_ollama_debug.py`
3. **Verify configuration:** Check `.env` file is correct
4. **Test connectivity:** Run `curl http://localhost:11434/api/tags`
5. **Check Ollama:** Run `ollama list` to see available models

---

## 📄 License

This project uses **Pipecat** framework under BSD 2-Clause License.  
See: https://github.com/pipecat-ai/pipecat/blob/main/LICENSE

---

## 🙏 Acknowledgments

Built with [Pipecat](https://github.com/pipecat-ai/pipecat) - The open-source framework for building voice and multimodal AI applications.

**Special thanks to:**
- Pipecat team for the amazing framework
- Ollama for local LLM support
- Deepgram for STT capabilities
- Google & OpenAI for cloud LLM APIs

## 🌐 Connect with Us

[![Facebook](https://img.shields.io/badge/Follow-Facebook-1877F2?logo=facebook&logoColor=white)](https://web.facebook.com/Playownai/)|
[![LinkedIn](https://img.shields.io/badge/Follow-LinkedIn-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/company/playownai)|
[![YouTube](https://img.shields.io/badge/Subscribe-@PlayOwnAi-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/@PlayOwnAi/)|