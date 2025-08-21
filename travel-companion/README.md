# Pipecat Travel Companion

Pipecat Travel Companion is a smart travel assistant powered by the `GeminiMultimodalLiveLLMService`. 
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

### 1. Setup Virtual Environment (Recommended)

Navigate to the `server` directory and set up a virtual environment:

```bash
cd server
python3 -m venv venv
source venv/bin/activate
```

### 2. Installation

Install the required dependencies in development mode:

```bash
pip install -r requirements.txt
```

### 3. Configuration

1. Copy the example environment configuration file:
   
```bash
cp env.example .env
```

2. Open `.env` and add your API keys and configuration details.

### 4. Running the Server

Start the server with the following command:

```bash
cd server
python src/server.py --host YOUR_IP
```
Replace `YOUR_IP` with your desired host IP address.

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

