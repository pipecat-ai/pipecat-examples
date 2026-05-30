# Video Transform

A Pipecat example demonstrating how to send and receive audio and video using `SmallWebRTCTransport`. This project also applies image processing to video frames using OpenCV.

## 🚀 Quick Start

### 1️⃣ Start the Bot Server

#### 📂 Navigate to the Server Directory
```bash
cd server
```

#### 🔧 Set Up the Environment
1. Install dependencies (uses [uv](https://docs.astral.sh/uv/)):
   ```bash
   uv sync
   ```

2. Configure environment variables:
   - Copy `env.example` to `.env`
   ```bash
   cp env.example .env
   ```
   - Add your API keys

#### ▶️ Run the Bot
```bash
uv run bot.py
```

> The first startup can take a little longer as Pipecat downloads the required models and dependencies.

### 2️⃣ Test with the Prebuilt UI

The development runner serves a prebuilt web UI for quick local testing:

- Open your browser and navigate to:
👉 http://localhost:7860
  - (Or use your custom host/port, e.g. `uv run bot.py --host 0.0.0.0 --port 8080`)

### 3️⃣ Connect Using a Custom Client App

For client-side setup, refer to the:
- [Typescript Guide](client/typescript/README.md).
- [iOS Guide](client/ios/README.md).

## ⚠️ Important Note
Ensure the bot server is running before using any client implementations.

## 📌 Requirements

- Python **3.10+**
- Node.js **16+** (for JavaScript components)
- Google API Key
- Modern web browser with WebRTC support

---

### 💡 Notes
- Ensure all dependencies are installed before running the server.
- Check the `.env` file for missing configurations.
- WebRTC requires a secure environment (HTTPS) for full functionality in production.

Happy coding! 🎉