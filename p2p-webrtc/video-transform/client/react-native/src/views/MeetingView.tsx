import {
  View,
  StyleSheet,
  Text,
  Image,
  TouchableOpacity,
} from 'react-native';

import React, {useState} from "react"

import { useVoiceClient } from '../context/VoiceClientContext';

import { Images } from '../theme/Assets';

import MicrophoneView from '../components/MicrophoneView';
import CameraButtonView from '../components/CameraButtonView';
import { SafeAreaView } from 'react-native-safe-area-context';
import Colors from '../theme/Colors';
import CustomButton from '../theme/CustomButton';
import {PipecatClientVideoView} from "@pipecat-ai/react-native-small-webrtc-transport";
import {ChatView} from "../components/ChatView";

const MeetingView: React.FC = () => {

  const { leave, toggleMicInput, toggleCamInput, remoteVideoTrack, messages } = useVoiceClient();

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.header}>
          <Image source={Images.dailyBot} style={styles.botImage} />
        </View>

        <View style={styles.mainPanel}>
          <PipecatClientVideoView
            videoTrack={remoteVideoTrack || null}
            audioTrack={null}
            style={styles.media}
            objectFit="cover"
          />

          {/* Floating chat overlay (bottom or top, adjust as needed) */}
          <View style={styles.overlay}>
            <ChatView messages={messages} />
            {/* Floating controls at the bottom */}
            <View style={styles.bottomControls}>
              <TouchableOpacity onPress={toggleMicInput}>
                <MicrophoneView style={styles.microphone} />
              </TouchableOpacity>
              <TouchableOpacity onPress={toggleCamInput}>
                <CameraButtonView style={styles.camera} />
              </TouchableOpacity>
            </View>
          </View>
        </View>

        {/* Bottom Panel */}
        <View style={styles.bottomPanel}>
          <CustomButton
            title="End"
            iconName={"exit-to-app"}
            onPress={leave}
            backgroundColor={Colors.black}
          />
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    width: "100%",
    backgroundColor: Colors.backgroundApp,
  },
  container: {
    flex: 1,
    padding: 20,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: 10,
  },
  botImage: {
    width: 48,
    height: 48,
  },
  mainPanel: {
    flex: 1,
    position: 'relative',       // Needed for all overlays to use as boundary
    width: '100%',
  },
  bottomControls: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    width: '100%',
    paddingBottom: 20,
  },
  microphone: {
    width: 160,
    height: 160,
  },
  camera: {
    width: 120,
    height: 120,
  },
  bottomPanel: {
    paddingVertical: 10,
  },
  endButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'black',
    borderRadius: 12,
    padding: 10,
  },
  endText: {
    marginLeft: 5,
    color: 'white',
  },
  media: {
    ...StyleSheet.absoluteFillObject,  // Video covers all
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    flex: 1
  },
});

export default MeetingView;