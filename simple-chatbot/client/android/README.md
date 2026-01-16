# Pipecat Demo Client for Android

Demo app which connects to an RTVI server, such as Pipecat, using the Pipecat Android client.

* Supports Daily and Small WebRTC transports
* Shows local and remove video streams
* Text and voice chat

<p align="center">
<img alt="main menu screenshot" src="files/screenshot_mainmenu.png" width="350px" /> <img alt="in-call screenshot" src="files/screenshot_call.png" width="350px" />
</p>

## How to run

```bash
# Build and install the app
./gradlew installDebug

# Launch the app
adb shell am start -n ai.pipecat.simple_chatbot_client/.MainActivity
```

Ensure that the `simple-chatbot` server is running as described in the parent README.

Use the command `adb reverse` to forward the necessary ports from your development machine to your Android device, and connect to the start URL:

```
http://localhost:7860/start
```
