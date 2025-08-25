# iOS Implementation

This guide provides instructions for setting up and running the iOS implementation of the Pipecat Travel Companion app. 
It utilizes the [Pipecat iOS SDK](https://docs.pipecat.ai/client/ios/introduction) to integrate location-based features and server interactions.

---

## Prerequisites

1. **Run the Bot Server**
   - Make sure the Pipecat Travel Companion server is running. Refer to the [server README](../../README) for setup instructions.

2. **Install Xcode**
   - Download and install [Xcode 15](https://developer.apple.com/xcode/).
   - Set up your device to run custom applications by following the guide on [distributing your app to registered devices](https://developer.apple.com/documentation/xcode/distributing-your-app-to-registered-devices).

---

## Running Locally

1. **Open the Project in Xcode**
   - Navigate to the project directory and open `TravelCompanion.xcodeproj` in Xcode.

2. **Build the Project**
   - Build the project by selecting your target device and clicking the "Build" button.

3. **Run on Your Device**
   - Connect your device to your computer.
   - Run the app by clicking the "Run" button.

4. **Connect to the Server**
   - Ensure the app is pointing to the correct server URL for testing. Update the configuration if needed.

---

## Troubleshooting

- **Build Errors**: Check if all dependencies are resolved and updated. Verify your Xcode version is 15 or above.
- **Connection Issues**: Ensure that the server is running and accessible from your device. Confirm the URL is correct.
- **Device Setup**: Make sure your device is properly registered and set up for development in Xcode.

---

## Additional Resources

- [Pipecat iOS SDK Documentation](https://docs.pipecat.ai/client/ios/introduction)
- [Xcode Documentation](https://developer.apple.com/documentation/xcode/)

---

Happy coding with Pipecat! 🚀

