#!/bin/bash
# clear
rm yarn.lock
rm -rf .expo
rm -rf ./ios/
rm -rf ./android/
rm -rf node_modules/
# Install dependencies
yarn install
# Before a native app can be compiled, the native source code must be generated.
npx expo prebuild
