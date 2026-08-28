"use client"

import type { Participant } from "@pipecat-ai/client-js"
import { RTVIEvent } from "@pipecat-ai/client-js"
import {
  usePipecatClient,
  usePipecatClientMediaTrack,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react"
import { useCallback, useEffect, useRef, useState } from "react"

import { AudioVisualizerBarView } from "@/components/pipecat/audio-visualizer-bar"
import {
  DeviceDropdown,
  DeviceDropdownContent,
  DeviceDropdownTrigger,
} from "@/components/pipecat/device-select"
import { cn } from "@/lib/utils"

const CONNECTED_STATES = ["connected", "ready"]

// The mic choice is held here rather than read from usePipecatClientMicControl.
// client.isMicEnabled bottoms out in daily-js's localAudio(), which reads a
// participant record daily commits *after* it emits track-started/track-stopped
// — so inside those events it still reports the pre-change value. client-react
// 1.8.2 syncs its own mic state from that read, which bounces the first toggle
// straight back and makes muting take two clicks. Of the three mic states
// (intent, device permission, transport track state) intent is the only one
// that is never transiently wrong, so it drives both the display and what the
// next click means.
const DEFAULT_MIC_ENABLED = true // matches usePipecatApp's enableMic option

export interface UserAudioControlProps {
  className?: string
}

/**
 * Mic level and device picker as one small bordered readout: the bars are
 * the mute toggle, the caret opens the input list. Green while the mic is
 * live, pink while it is muted — or while there is no session to talk
 * into. Must be rendered inside a PipecatClientProvider.
 */
export function UserAudioControl({ className }: UserAudioControlProps) {
  const client = usePipecatClient()
  const transportState = usePipecatClientTransportState()
  const track = usePipecatClientMediaTrack("audio", "local")
  const [micEnabled, setMicEnabled] = useState(DEFAULT_MIC_ENABLED)

  const isConnected = CONNECTED_STATES.includes(transportState)
  const live = isConnected && micEnabled

  const setMic = useCallback(
    (enabled: boolean) => {
      setMicEnabled(enabled)
      client?.enableMic(enabled)
    },
    [client]
  )

  // A mute chosen before connecting has to be re-asserted once there is a
  // session to apply it to: daily's startCamera does not reliably honour
  // startAudioOff, so the mic can come up live regardless of the choice.
  // Read through a ref so this fires on the connect edge only, not on every
  // toggle — setMic already pushes those through.
  const micEnabledRef = useRef(micEnabled)
  micEnabledRef.current = micEnabled
  useEffect(() => {
    if (!isConnected || !client) return
    client.enableMic(micEnabledRef.current)
  }, [isConnected, client])

  // Re-sync from the client for changes we didn't make (a device going away,
  // a transport-side stop). Deferred to a microtask so the read lands after
  // daily's participant commit — correct under either ordering — and ignoring
  // the non-boolean it returns before a local participant exists, since
  // coercing that to false is what inverts the control pre-connect.
  const reconcile = useCallback(() => {
    queueMicrotask(() => {
      const actual = client?.isMicEnabled
      if (typeof actual === "boolean") setMicEnabled(actual)
    })
  }, [client])

  const onLocalAudioTrack = useCallback(
    (changed: MediaStreamTrack, participant?: Participant) => {
      if (participant?.local && changed.kind === "audio") reconcile()
    },
    [reconcile]
  )
  useRTVIClientEvent(RTVIEvent.TrackStarted, onLocalAudioTrack)
  useRTVIClientEvent(RTVIEvent.TrackStopped, onLocalAudioTrack)

  return (
    <DeviceDropdown kind="audioinput">
      <div
        data-slot="user-audio-control"
        data-state={live ? "active" : "inactive"}
        className={cn(
          "flex h-7 shrink-0 items-center border",
          live ? "border-active/50" : "border-inactive/50",
          className
        )}
      >
        <button
          type="button"
          onClick={() => setMic(!micEnabled)}
          aria-pressed={micEnabled}
          aria-label={micEnabled ? "Mute microphone" : "Unmute microphone"}
          className="flex h-full items-center gap-2 px-2"
        >
          {/* Mic state at a glance, before the bars say anything. */}
          <span
            className={cn(
              "h-2 w-[3px] shrink-0",
              live ? "bg-active" : "bg-inactive"
            )}
          />
          <AudioVisualizerBarView
            track={live ? track : null}
            barColor={live ? "--active-background" : "--inactive-background"}
            barCount={7}
            barWidth={3}
            barGap={3}
            barMaxHeight={12}
            barOrigin="center"
            barLineCap="square"
            noPeaks
            className="w-auto"
          />
        </button>
        <span
          className={cn("h-full w-px", live ? "bg-active/40" : "bg-inactive/40")}
        />
        <DeviceDropdownTrigger
          render={
            <button
              type="button"
              aria-label="Audio devices"
              className={cn(
                "flex h-full items-center px-2 text-[13px] leading-none",
                live ? "text-active" : "text-inactive"
              )}
            >
              ∨
            </button>
          }
        />
      </div>
      <DeviceDropdownContent className="w-auto min-w-64" />
    </DeviceDropdown>
  )
}
