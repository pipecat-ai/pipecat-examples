# 🤖 Pipecat Multi-LLM Fallback Example with Runtime Error Recovery

### Author: **Abdul Matin**  
**Company:** PlayOwnAI  
📧 **Email:** playownai@gmail.com  
🔗 **GitHub:** [matinict](https://github.com/matinict)

---
  
## 📘 Overview

This example demonstrates a **robust multi-LLM fallback mechanism** built using **[Pipecat](https://github.com/pipecat-ai/pipecat)**.  
It automatically recovers from runtime errors and switches between available Large Language Models (LLMs) — ensuring your AI assistant always stays responsive.

---


### 📺 Watch Pipecat Demo Our Channel  
[PlayOwnDemo on YouTube](https://youtu.be/URnVU5OyEQI)


## ⚙️ How It Works

1️⃣ Tries **Ollama local LLM** (fastest and privacy-friendly)  
2️⃣ If unavailable → switches to **Google Gemini** (via API key)  
3️⃣ If that fails → falls back to **OpenAI GPT-4 or GPT-4o-mini**  
4️⃣ If all fail → gracefully exits with a helpful message  

The bot listens to **voice input** and replies **naturally**, using either local or cloud models depending on availability.

---

## 🧩 Required Services

| Service | Purpose | Notes |
|----------|----------|-------|
| **Deepgram** | Speech-to-Text (STT) | Required |
| **Cartesia** | Text-to-Speech (TTS) | Optional but recommended |
| **Ollama** | Local LLM | Recommended for offline mode |
| **Google Gemini / OpenAI** | Cloud fallback LLMs | Optional (via API keys) |

---

## 🧰 Environment Variables

Create a `.env` file in the project root and set your credentials:

```bash
DEEPGRAM_API_KEY=your_deepgram_key
CARTESIA_API_KEY=your_cartesia_key
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:latest
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key



## 🌐 Connect with Us

[![Facebook](https://img.shields.io/badge/Follow-Facebook-1877F2?logo=facebook&logoColor=white)](https://web.facebook.com/Playownai/)  
[![LinkedIn](https://img.shields.io/badge/Follow-LinkedIn-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/company/playownai)  
[![YouTube](https://img.shields.io/badge/Subscribe-@PlayOwnAi-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/@PlayOwnAi/)
