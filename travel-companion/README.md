# Pipecat Travel Companion

Pipecat Travel Companion is a smart travel assistant powered by the `GeminiLiveLLMService`.
It offers personalized recommendations and services like checking the weather, suggesting nearby restaurants,
and providing recent news based on your current location.

---

## Features

- **Location Sharing**:
  - Retrieves your current location using the `get_my_current_location` RTVI function calling.
  - Shares selected restaurant locations using the `set_restaurant_location` RTVI function calling, which opens Google Maps on iOS.
- **Weather Updates**: Uses `google_search` to check and share the current weather.
- **Restaurant Recommendations**: Suggests restaurants near your current location using `google_search`.
- **Local News**: Provides relevant and recent news from your location using `google_search`.

---

## Getting Started

Follow these steps to set up and run the Pipecat Travel Companion server.

### 1. Navigate to Server Directory

```bash
cd server
```

### 2. Installation

Install the required dependencies:

```bash
uv sync
```

### 3. Configuration

Copy the example environment configuration file:

```bash
cp env.example .env
```

Open `.env` and add your API keys and configuration details.

### 4. Running the Server

Start the server with the following command:

```bash
uv run bot.py -t daily
```

---

## Client APP

This project is designed to work with a companion iOS app. The app:

- Uses RTVI function calls to share the user's current location with the LLM.
- Receives restaurant location suggestions from the LLM and opens Google Maps to display the location.

For detailed instructions on setting up and running the iOS app, refer to [this link](./client/ios/README.md).

---

## Additional Notes

- Ensure all required API keys are defined.

---

Happy travels with Pipecat! 🌍
