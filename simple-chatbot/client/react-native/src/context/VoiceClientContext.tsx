import React, { createContext, useState, useContext, ReactNode, useCallback, useMemo, useRef, useEffect } from 'react'
import Toast from 'react-native-toast-message'
import { RNDailyTransport } from '@pipecat-ai/react-native-daily-transport'
import { PipecatClient, TransportState, Participant } from '@pipecat-ai/client-js'
import { MediaStreamTrack } from '@daily-co/react-native-webrtc'
import { SettingsManager } from '../settings/SettingsManager';

interface VoiceClientContextProps {
  voiceClient: PipecatClient | null
  inCall: boolean
  currentState: string
  botReady: boolean
  localAudioLevel: number
  remoteAudioLevel: number
  isMicEnabled: boolean
  isCamEnabled: boolean
  videoTrack?: MediaStreamTrack
  // methods
  start: (url: string) => Promise<void>
  leave: () => void
  toggleMicInput: () => void
  toggleCamInput: () => void
}

export const VoiceClientContext = createContext<VoiceClientContextProps | undefined>(undefined)

interface VoiceClientProviderProps {
  children: ReactNode
}

export const VoiceClientProvider: React.FC<VoiceClientProviderProps> = ({ children }) => {

  const [voiceClient, setVoiceClient] = useState<PipecatClient | null>(null)
  const [inCall, setInCall] = useState<boolean>(false)
  const [currentState, setCurrentState] = useState<TransportState>("disconnected")
  const [botReady, setBotReady] = useState<boolean>(false)
  const [isMicEnabled, setIsMicEnabled] = useState<boolean>(false)
  const [isCamEnabled, setIsCamEnabled] = useState<boolean>(false)
  const [videoTrack, setVideoTrack] = useState<MediaStreamTrack>()
  const [localAudioLevel, setLocalAudioLevel] = useState<number>(0)
  const [remoteAudioLevel, setRemoteAudioLevel] = useState<number>(0)
  const botSpeakingRef = useRef(false)

  const handleError = useCallback((error: any) => {
    console.log("Error occurred:", error)
    const errorMessage = error.message || error.data?.error || "An unexpected error occurred"
    Toast.show({
      type: 'error',
      text1: errorMessage,
    })
  }, [])

  const createVoiceClient = useCallback((): PipecatClient => {
    const inCallStates = new Set(["authenticating", "authenticated", "connecting", "connected", "ready"])
    const client = new PipecatClient({
      transport: new RNDailyTransport(),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (state) => {
          setCurrentState(state)
          setInCall(inCallStates.has(state))
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
        onLocalAudioLevel: (level: number) => {
          setLocalAudioLevel(level)
        },
        onRemoteAudioLevel: (level: number) => {
          if (botSpeakingRef.current) {
            setRemoteAudioLevel(level)
          }
        },
        onBotStartedSpeaking: () => {
          botSpeakingRef.current = true
        },
        onBotStoppedSpeaking: () => {
          botSpeakingRef.current = false
          setRemoteAudioLevel(0)
        },
        onConnected: () => {
          setIsMicEnabled(client.isMicEnabled)
          setIsCamEnabled(client.isCamEnabled)
        },
        onTrackStarted: (track: MediaStreamTrack, p?: Participant) => {
          if (p?.local && track.kind === 'video'){
            setVideoTrack(track)
          }
        }
      },
    })
    return client
  }, [handleError])

  const start = useCallback(async (url: string): Promise<void> => {
    const client = createVoiceClient()
    setVoiceClient(client)
    try {
      await client?.initDevices()
      await client?.startBotAndConnect({
        endpoint: url + '/start',
        requestData: {
          createDailyRoom: true,
        },
      });
      // updating the preferences
      const newSettings = await SettingsManager.getSettings();
      newSettings.backendURL = url
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

  useEffect(() => {
    return () => {
      if (voiceClient) {
        voiceClient.removeAllListeners() // Cleanup on unmount
      }
    }
  }, [voiceClient])

  const contextValue = useMemo(() => ({
    voiceClient,
    inCall,
    currentState,
    botReady,
    isMicEnabled,
    isCamEnabled,
    localAudioLevel,
    remoteAudioLevel,
    videoTrack,
    start,
    leave,
    toggleMicInput,
    toggleCamInput
  }), [voiceClient, inCall, currentState, botReady, isMicEnabled, isCamEnabled, localAudioLevel, remoteAudioLevel, videoTrack, start, leave, toggleMicInput, toggleCamInput])

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
