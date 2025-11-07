// Disabling the logs from react-native-webrtc
import debug from 'debug';
debug.disable('rn-webrtc:*');

// Ignoring the warnings from react-native-background-timer while they don't fix this issue:
// https://github.com/ocetnik/react-native-background-timer/issues/366
import { LogBox } from 'react-native';
LogBox.ignoreLogs([
  '`new NativeEventEmitter()` was called with a non-null argument without the required `addListener` method.',
  '`new NativeEventEmitter()` was called with a non-null argument without the required `removeListeners` method.',
]);

import { registerRootComponent } from 'expo';

import App from './src/App';

// registerRootComponent calls AppRegistry.registerComponent('main', () => App);
// It also ensures that whether you load the app in Expo Go or in a native build,
// the environment is set up appropriately
registerRootComponent(App);
