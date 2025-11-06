# React Native implementation

Basic implementation using the [Pipecat RN SDK](https://docs.pipecat.ai/client/react-native/introduction).

## Usage

### Expo requirements

This project cannot be used with an [Expo Go](https://docs.expo.dev/workflow/expo-go/) app because [it requires custom native code](https://docs.expo.io/workflow/customizing/).

When a project requires custom native code or a config plugin, we need to transition from using [Expo Go](https://docs.expo.dev/workflow/expo-go/)
to a [development build](https://docs.expo.dev/development/introduction/).

More details about the custom native code used by this demo can be found in [rn-daily-js-expo-config-plugin](https://github.com/daily-co/rn-daily-js-expo-config-plugin).

### Building remotely

If you do not have experience with Xcode and Android Studio builds or do not have them installed locally on your computer, you will need to follow [this guide from Expo to use EAS Build](https://docs.expo.dev/development/create-development-builds/#create-and-install-eas-build).

### Building locally

You will need to have installed locally on your computer:

- [Xcode](https://developer.apple.com/xcode/) to build for iOS;
- [Android Studio](https://developer.android.com/studio) to build for Android;

#### Install the demo dependencies

```bash
# Use the version of node specified in .nvmrc
nvm i

# Install dependencies
yarn install

# Before a native app can be compiled, the native source code must be generated.
npx expo prebuild

# Copy the template and configure the environment variables
cp env.example .env
```

#### Running on Android

After plugging in an Android device [configured for debugging](https://developer.android.com/studio/debug/dev-options), run the following command:

```
npm run android
```

#### Running on iOS

Run the following command:

```
npm run ios
```

**Troubleshooting common errors:**

- If you see the error `Change your bundle identifier to a unique string to try again`, update the "Bundle Identifier" input in `Signing & Capabilities` to make it unique. This should resolve the error.

- If you see an error that says `Xcode was unable to launch because it has an invalid code signature, inadequate entitlements or its profile has not been explicitly trusted by the user`, you may need to update the settings on your iPhone to enable the required permissions as follows:

1. Open `Settings` on your iPhone
1. Select `General`, then `Device Management`
1. Click `Trust` for DailyPlayground

- You may also be prompted to enter you login keychain password. Be sure to click `Always trust` to avoid the prompt showing multiple times.