# Pipecat Simple Chatbot Client for Android

Demo app which connects to the `simple-chatbot` backend over RTVI.

## Screenshot

<img alt="screenshot" src="files/screenshot.jpg" width="400px" />

## How to run

```bash
# Build and install the app
./gradlew installDebug

# Launch the app
adb shell am start -n ai.pipecat.simple_chatbot_client/.MainActivity
```

Ensure that the `simple-chatbot` server is running as described in the parent README.
