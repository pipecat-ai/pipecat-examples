import React, { createContext, useState, useContext, ReactNode, useCallback, useMemo, useRef, useEffect } from 'react'
import Toast from 'react-native-toast-message'
import {
  RNSmallWebRTCTransport,
  SmallWebRTCTransportConstructorOptions,
} from '@pipecat-ai/react-native-small-webrtc-transport';

import {
  APIRequest,
  PipecatClient,
  TransportState,
  Participant
} from '@pipecat-ai/client-js';

import { DailyMediaManager } from '@pipecat-ai/react-native-daily-media-manager';
import { MediaStreamTrack } from '@daily-co/react-native-webrtc'
import { SettingsManager } from '../settings/SettingsManager';

interface VoiceClientContextProps {
  voiceClient: PipecatClient | null
  inCall: boolean
  currentState: string
  botReady: boolean
  localAudioLevel: number
  isMicEnabled: boolean
  isCamEnabled: boolean
  localVideoTrack?: MediaStreamTrack
  remoteVideoTrack?: MediaStreamTrack
  // methods
  start: (url: string, authorizationToken:string) => Promise<void>
  leave: () => void
  toggleMicInput: () => void
  toggleCamInput: () => void,
  messages: LiveMessage[]
}

export const VoiceClientContext = createContext<VoiceClientContextProps | undefined>(undefined)

interface VoiceClientProviderProps {
  children: ReactNode
}

export type MessageType = 'bot' | 'user' | 'system'

export interface LiveMessage {
  id: string;
  content: string
  type: MessageType
  updatedAt: Date
}

export const VoiceClientProvider: React.FC<VoiceClientProviderProps> = ({ children }) => {

  const [voiceClient, setVoiceClient] = useState<PipecatClient | null>(null)
  const [inCall, setInCall] = useState<boolean>(false)
  const [currentState, setCurrentState] = useState<TransportState>("disconnected")
  const [botReady, setBotReady] = useState<boolean>(false)
  const [isMicEnabled, setIsMicEnabled] = useState<boolean>(false)
  const [isCamEnabled, setIsCamEnabled] = useState<boolean>(false)
  const [localVideoTrack, setLocalVideoTrack] = useState<MediaStreamTrack | undefined>()
  const [remoteVideoTrack, setRemoteVideoTrack] = useState<MediaStreamTrack | undefined>()
  const [localAudioLevel, setLocalAudioLevel] = useState<number>(0)
  // For controlling mock audio timer:
  const mockAudioTimer = useRef<NodeJS.Timeout | null>(null)
  const botSpeakingRef = useRef(false)
  // Live messages to the chat
  const [messages, setMessages] = useState<LiveMessage[]>([])

  const handleError = useCallback((error: any) => {
    console.log("Error occurred:", error)
    const errorMessage = error.message || error.data?.error || "An unexpected error occurred"
    Toast.show({
      type: 'error',
      text1: errorMessage,
    })
  }, [])

  // --- mock audio logic while SmallWebRTC does not support audio level ---
  const startMockAudioLevel = useCallback(() => {
    if (mockAudioTimer.current) return;
    mockAudioTimer.current = setInterval(() => {
      // Simulate value between 0.1 and 1.0 (e.g. for "speaking" user)
      setLocalAudioLevel(Math.random() * 0.8 + 0.2)
    }, 100)
  }, [])

  const stopMockAudioLevel = useCallback(() => {
    if (mockAudioTimer.current) {
      clearInterval(mockAudioTimer.current)
      mockAudioTimer.current = null
    }
    setLocalAudioLevel(0)
  }, [])

  const createVoiceClient = useCallback((): PipecatClient => {
    const inCallStates = new Set(["authenticating", "authenticated", "connecting", "connected", "ready"])
    const options: SmallWebRTCTransportConstructorOptions = {
      mediaManager: new DailyMediaManager(),
    };
    const client = new PipecatClient({
      transport: new RNSmallWebRTCTransport(options),
      enableMic: true,
      enableCam: true,
      callbacks: {
        onTransportStateChanged: (state) => {
          setCurrentState(state)
          setInCall(inCallStates.has(state))
          createLiveMessage(state, 'system')
        },
        onError: (error) => {
          handleError(error)
        },
        onBotReady: () => {
          setBotReady(true)
        },
        onDisconnected: () => {
          setBotReady(false)
          setIsMicEnabled(false)
          setIsCamEnabled(false)
        },
        // TODO: SmallWebRTC doesn't support this event yet.
        /*onLocalAudioLevel: (level: number) => {
          setLocalAudioLevel(level)
        },*/
        onUserStartedSpeaking:() => {
          createLiveMessage("User started speaking", "system")
          startMockAudioLevel()
        },
        onUserStoppedSpeaking:() => {
          createLiveMessage("User stopped speaking", "system")
          stopMockAudioLevel()
        },
        onUserTranscript:(data) => {
          createLiveMessage(data.text, "user")
        },
        onBotStartedSpeaking: () => {
          createLiveMessage("Bot started speaking", "system")
          botSpeakingRef.current = true
          createLiveMessage("", "bot")
        },
        onBotStoppedSpeaking: () => {
          createLiveMessage("Bot stopped speaking", "system")
          botSpeakingRef.current = false
        },
        onBotTtsText:(data) => {
          appendTextToLiveMessage(data.text)
        },
        onConnected: () => {
          setIsMicEnabled(client.isMicEnabled)
          setIsCamEnabled(client.isCamEnabled)
          client.updateMic("SPEAKERPHONE")
        },
        onTrackStarted: (track: MediaStreamTrack, p?: Participant) => {
          if (track.kind !== 'video') {
            return
          }
          if (p?.local){
            setLocalVideoTrack(track)
          } else {
            setRemoteVideoTrack(track)
          }
        },
        onTrackStopped: (track: MediaStreamTrack, p?: Participant) => {
          if (track.kind !== 'video') {
            return
          }
          if (p?.local){
            setLocalVideoTrack(undefined)
          } else {
            setRemoteVideoTrack(undefined)
          }
        }
      },
    })
    return client
  }, [handleError, startMockAudioLevel, stopMockAudioLevel])

  const start = useCallback(async (url: string, authorizationToken:string): Promise<void> => {
    resetLiveMessages()
    const client = createVoiceClient()
    setVoiceClient(client)
    try {
      await client?.initDevices()
      const connectParams: APIRequest = {
        endpoint: url + '/start',
        requestData: {
          createDailyRoom: false,
          enableDefaultIceServers: true,
        },
      };
      if (authorizationToken.trim()) {
        const headers = new Headers();
        headers.append('Authorization', `Bearer ${authorizationToken}`);
        connectParams.headers = headers;
      }
      await client?.startBotAndConnect(connectParams);
      // updating the preferences
      const newSettings = await SettingsManager.getSettings();
      newSettings.backendURL = url
      newSettings.authorizationToken = authorizationToken
      await SettingsManager.updateSettings(newSettings)
    } catch (error) {
      handleError(error)
    }
  }, [createVoiceClient, handleError])

  const leave = useCallback(async (): Promise<void> => {
    if (voiceClient) {
      await voiceClient.disconnect()
      setVoiceClient(null)
    }
  }, [voiceClient])

  const toggleMicInput = useCallback(async (): Promise<void> => {
    if (voiceClient) {
      try {
        let enableMic = !isMicEnabled
        voiceClient.enableMic(enableMic)
        setIsMicEnabled(enableMic)
      } catch (e) {
        handleError(e)
      }
    }
  }, [voiceClient, isMicEnabled])

  const toggleCamInput = useCallback(async (): Promise<void> => {
    if (voiceClient) {
      try {
        let enableCam = !isCamEnabled
        voiceClient.enableCam(enableCam)
        setIsCamEnabled(enableCam)
      } catch (e) {
        handleError(e)
      }
    }
  }, [voiceClient, isCamEnabled])

  const createLiveMessage = useCallback((content: string, type: MessageType) => {
    const uniqueId = Date.now().toString(36) + Math.random().toString(36).substring(2, 9);
    const liveMessage: LiveMessage = {
      content,
      type,
      updatedAt: new Date(),
      id: uniqueId
    }
    setMessages(prev => [...prev, liveMessage])
  }, [])

  const appendTextToLiveMessage = useCallback((content: string) => {
    setMessages(prevMessages => {
      if (prevMessages.length) {
        const lastBotIndex = [...prevMessages].reverse().findIndex(msg => msg.type === "bot");
        if (lastBotIndex !== -1) {
          const realIndex = prevMessages.length - 1 - lastBotIndex;
          prevMessages[realIndex]!.content = prevMessages[realIndex]!.content + content
        }
      }
      return [...prevMessages]
    });
  }, []);

  const resetLiveMessages = useCallback(() => {
    setMessages([])
  }, [])

  useEffect(() => {
    return () => {
      if (voiceClient) {
        voiceClient.removeAllListeners() // Cleanup on unmount
        resetLiveMessages()
      }
    }
  }, [voiceClient])

  // Cleanup interval when unmounting
  useEffect(() => {
    return () => {
      if (mockAudioTimer.current) clearInterval(mockAudioTimer.current)
    }
  }, [])

  const contextValue = useMemo(() => ({
    voiceClient,
    inCall,
    currentState,
    botReady,
    isMicEnabled,
    isCamEnabled,
    localAudioLevel,
    localVideoTrack,
    remoteVideoTrack,
    start,
    leave,
    toggleMicInput,
    toggleCamInput,
    messages
  }), [voiceClient, inCall, currentState, botReady, isMicEnabled, isCamEnabled, localAudioLevel, localVideoTrack, remoteVideoTrack, start, leave, toggleMicInput, toggleCamInput, messages])

  return (
    <VoiceClientContext.Provider value={contextValue}>
      {children}
    </VoiceClientContext.Provider>
  )
}

export const useVoiceClient = (): VoiceClientContextProps => {
  const context = useContext(VoiceClientContext)
  if (!context) {
    throw new Error('useVoiceClient must be used within a VoiceClientProvider')
  }
  return context
}