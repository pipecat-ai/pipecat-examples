import { RTVIEvent } from "@pipecat-ai/client-js"
import {
  PipecatClientProvider,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react"
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport"
import { Loader2Icon } from "lucide-react"
import { useCallback, useEffect, useState } from "react"

import { AudioVisualizerBar } from "@/components/pipecat/audio-visualizer-bar"
import { BotAudioOutput } from "@/components/pipecat/bot-audio"
import { ConnectButton } from "@/components/pipecat/connect-button"
import { Conversation } from "@/components/pipecat/conversation"
import { TextInput } from "@/components/pipecat/text-input"
import { UserAudioControl } from "@/components/pipecat/user-audio-control"
import { Separator } from "@/components/ui/separator"
import { usePipecatApp } from "@/hooks/use-pipecat-app"
import { EMPTY_VOICE, loadVoice, type VoiceInfo } from "@/voice"

/** The voice described in public/voice.json, loaded once. */
function useVoice(): VoiceInfo {
  const [voice, setVoice] = useState<VoiceInfo>(EMPTY_VOICE)
  useEffect(() => {
    let alive = true
    loadVoice().then((info) => {
      if (alive) setVoice(info)
    })
    return () => {
      alive = false
    }
  }, [])
  return voice
}

/** True while the bot is talking; false again on silence or disconnect. */
function useBotSpeaking(): boolean {
  const [speaking, setSpeaking] = useState(false)
  const transportState = usePipecatClientTransportState()

  useRTVIClientEvent(
    RTVIEvent.BotStartedSpeaking,
    useCallback(() => setSpeaking(true), [])
  )
  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => setSpeaking(false), [])
  )
  // Hanging up mid-sentence means no BotStoppedSpeaking ever arrives, so clear
  // the flag on disconnect too; otherwise the next session starts mid-glow.
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => setSpeaking(false), [])
  )
  return speaking && transportState === "ready"
}

/**
 * The stage above the transcript: the reference image the voice was designed from
 * when there is one (it glows while the bot speaks), otherwise the bot's audio
 * visualizer.
 */
function Stage({ voice }: { voice: VoiceInfo }) {
  const speaking = useBotSpeaking()
  const transportState = usePipecatClientTransportState()
  const connecting =
    transportState === "connecting" || transportState === "authenticating"

  if (voice.image) {
    return (
      <section className="stage" aria-label="Voice portrait">
        <img
          className="stage-image"
          src={voice.image}
          alt={voice.name ?? "The voice"}
          data-speaking={speaking ? "true" : "false"}
        />
      </section>
    )
  }

  return (
    <section className="stage" aria-label="Bot audio">
      <div className="stage-visualizer bg-accent text-primary rounded-xl">
        <div className="stage-visualizer-canvas">
          <AudioVisualizerBar
            participantType="bot"
            barCount={5}
            barWidth={36}
            barGap={14}
            barMaxHeight={140}
            isConnecting={connecting}
          />
        </div>
      </div>
    </section>
  )
}

function Shell({
  voice,
  connect,
  disconnect,
  error,
}: {
  voice: VoiceInfo
  connect: () => Promise<void>
  disconnect: () => Promise<void>
  error: string | null
}) {
  const name = voice.name ?? "Gradium voice"

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">{name}</h1>
        {voice.brief && <p className="app-brief">{voice.brief}</p>}
      </header>

      <Stage voice={voice} />

      <section className="transcript" aria-label="Transcript">
        <Conversation assistantLabel={voice.name ?? "bot"} clientLabel="you" />
      </section>

      <footer className="app-footer">
        {error && (
          <p role="alert" className="app-error">
            {error}
          </p>
        )}
        <div className="control-bar">
          <UserAudioControl />
          <Separator orientation="vertical" className="control-bar-divider" />
          <TextInput placeholder="Type to the bot…" className="control-bar-text" />
          <Separator orientation="vertical" className="control-bar-divider" />
          <ConnectButton onConnect={connect} onDisconnect={disconnect} />
        </div>
      </footer>
    </div>
  )
}

export function App() {
  const voice = useVoice()
  // The WebRTC offer goes to /api/offer, which vite.config.ts proxies to the bot.
  // (A top-level `endpoint` key would mean "start a bot first", which the Pipecat
  // dev runner does not serve; the SmallWebRTC connection params go in as-is.)
  const { client, connect, disconnect, error } = usePipecatApp({
    transportFactory: () => new SmallWebRTCTransport(),
    connectParams: { webrtcRequestParams: { endpoint: "/api/offer" } },
    initDevicesOnMount: true,
  })

  if (!client) {
    return (
      <div className="app-loading">
        {error ? (
          <p role="alert" className="app-error">
            {error}
          </p>
        ) : (
          <Loader2Icon className="animate-spin" aria-label="Loading" />
        )}
      </div>
    )
  }

  return (
    <PipecatClientProvider client={client}>
      <BotAudioOutput />
      <Shell voice={voice} connect={connect} disconnect={disconnect} error={error} />
    </PipecatClientProvider>
  )
}

export default App
