# Voice Agent Docker example

A Pipecat example demonstrating the simplest way to create a voice agent using `SmallWebRTCTransport` with Docker.

## 🚀 Quick Start

### 1️⃣ Build the Bot Server

1. **Configure environment variables:**

   ```bash
   cp env.example .env
   ```

   - Then edit `.env` to include your API keys.

2. **Build the Docker container:**

   ```bash
   uv sync
   docker build -t small-webrtc-bot .
   ```

---

### ▶️ Run the Bot Server

#### ✅ **Linux**

On Linux, Docker allows advanced networking options (like exposing UDP port ranges), which are required for direct WebRTC peer-to-peer connections.

```bash
# Run in the background using host networking (preferred for local dev)
docker run -d --network=host --name small-webrtc-bot small-webrtc-bot:latest

# Or, expose individual ports explicitly
docker run --rm \
  --sysctl net.ipv4.ip_local_port_range="40000 40100" \
  -p 7860:7860 \
  -p 40000-40100:40000-40100/udp \
  --name small-webrtc-bot \
  small-webrtc-bot:latest
```
> ⚠️ **Port Range Limitation**
>
> `SmallWebRTCConnection` uses aiortc, which relies on aioice for ICE transport. There is a known limitation ([aiortc/aioice#47](https://github.com/aiortc/aioice/issues/47)) where port control for `gather_candidates` is not fully supported. The Docker configuration above provides a Linux-specific workaround by:
> 1. Limiting the ephemeral port range the container can use (`--sysctl net.ipv4.ip_local_port_range`)
> 2. Explicitly exposing only those allowed ports (`-p 40000-40100:40000-40100/udp`)
>
> This ensures predictable port usage for WebRTC connections on Linux.

#### 🍏 **macOS (and Windows via Docker Desktop)**

Docker Desktop on macOS does **not support `--network=host`**, and UDP port forwarding has known limitations.

```bash
docker run --rm \
  -p 7860:7860 \
  --name small-webrtc-bot \
  small-webrtc-bot:latest
```

> ⚠️ **On macOS, a TURN server is needed**  
> Because we can not configure which UDP ports aiortc it is going to use, direct WebRTC peer-to-peer connections are unlikely to succeed.  
> A TURN server is required to relay media traffic between the client and the bot when NAT traversal fails.

---

### 2️⃣ Connect Using the Client App

Open your browser and go to:

```
http://localhost:7860
```

---

## WebRTC ICE Servers Configuration

When implementing WebRTC in your project, **STUN** (Session Traversal Utilities for NAT) and **TURN** (Traversal Using Relays around NAT) 
servers are usually needed in cases where users are behind routers or firewalls.

In local networks (e.g., testing within the same home or office network), you usually don’t need to configure STUN or TURN servers. 
In such cases, WebRTC can often directly establish peer-to-peer connections without needing to traverse NAT or firewalls.

### What are STUN and TURN Servers?

- **STUN Server**: Helps clients discover their public IP address and port when they're behind a NAT (Network Address Translation) device (like a router). 
This allows WebRTC to attempt direct peer-to-peer communication by providing the public-facing IP and port.
  
- **TURN Server**: Used as a fallback when direct peer-to-peer communication isn't possible due to strict NATs or firewalls blocking connections. 
The TURN server relays media traffic between peers.

### Why are ICE Servers Important?

**ICE (Interactive Connectivity Establishment)** is a framework used by WebRTC to handle network traversal and NAT issues. 
The `iceServers` configuration provides a list of **STUN** and **TURN** servers that WebRTC uses to find the best way to connect two peers. 

### Example Configuration for ICE Servers

Here’s how you can configure a basic `iceServers` object in WebRTC for testing purposes, using Google's public STUN server:

```javascript
const config = {
  iceServers: [
    {
      urls: ["stun:stun.l.google.com:19302"], // Google's public STUN server
    }
  ],
};
```

> For testing purposes, you can either use public **STUN** servers (like Google's) or set up your own **TURN** server. 
If you're running your own TURN server, make sure to include your server URL, username, and credential in the configuration.

> 🧪 For local Linux tests, STUN alone may work.  
> 🍏 On macOS or behind strict NAT/firewall, TURN is **required**.

---

## 📋 Requirements

- Docker (Docker Desktop for macOS/Windows)
- Google API Key (or your own STT/TTS provider)
- Modern WebRTC-compatible browser (e.g., Chrome, Firefox)

---

## 📝 Notes

- Check `.env` for required API credentials.
- On macOS or Windows, don't rely on `--network=host`.
- In production, WebRTC apps **must** run over HTTPS.
- Consider deploying your own TURN server or using a provider like Twilio or coturn.

---

Happy coding! 🎉
