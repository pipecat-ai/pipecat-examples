"use client"

import type { BotReadyData } from "@pipecat-ai/client-js"
import { RTVIEvent } from "@pipecat-ai/client-js"
import { usePipecatClient, useRTVIClientEvent } from "@pipecat-ai/client-react"
import { useCallback, useEffect, useRef, useState } from "react"

import { usePipecatMetricValue } from "@/hooks/use-pipecat-metrics"

export interface SessionLogEntry {
  id: string
  /** Epoch ms — the transcript interleaves these with conversation messages. */
  at: number
  text: string
}

/**
 * The session's own narration: the lines a terminal prints around the
 * conversation rather than in it — the session opening, each turn closing
 * with the latency it took, the session ending. Cleared when a new session
 * connects. Must be rendered inside a PipecatClientProvider.
 */
export function useSessionLog(): SessionLogEntry[] {
  const [entries, setEntries] = useState<SessionLogEntry[]>([])
  const nextId = useRef(0)

  // Read at event time, not render time: a turn's latency is whatever the
  // last ttfa metric said when the bot stopped speaking.
  const ttfa = usePipecatMetricValue("ttfa")
  const ttfaRef = useRef(ttfa)
  useEffect(() => {
    ttfaRef.current = ttfa
  }, [ttfa])

  const append = useCallback((text: string) => {
    setEntries((current) => [
      ...current,
      { id: `log-${nextId.current++}`, at: Date.now(), text },
    ])
  }, [])

  useRTVIClientEvent(
    RTVIEvent.Connected,
    useCallback(() => {
      nextId.current = 1
      setEntries([
        {
          id: "log-0",
          at: Date.now(),
          text: "session started · webrtc connected",
        },
      ])
    }, [])
  )

  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => {
      const seconds = ttfaRef.current
      append(
        seconds === null
          ? "turn complete"
          : `turn complete · ${Math.round(seconds * 1000)}ms ttfat`
      )
    }, [append])
  )

  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => append("session ended"), [append])
  )

  return entries
}

export interface SessionVersions {
  /** RTVI protocol version the bot reported, or null before bot-ready. */
  rtvi: string | null
  /** The client SDK's own version. */
  client: string
}

/**
 * Which protocol the two ends of the session settled on. The RTVI version
 * is the bot's, and only exists once it has sent its bot-ready payload —
 * so there is nothing to report until there is a session to describe.
 * Must be rendered inside a PipecatClientProvider.
 */
export function useSessionVersions(): SessionVersions {
  const client = usePipecatClient()
  const [rtvi, setRtvi] = useState<string | null>(null)

  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback((data: BotReadyData) => setRtvi(data.version), [])
  )

  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => setRtvi(null), [])
  )

  return { rtvi, client: client?.version ?? "" }
}

/** Whether the bot currently holds the floor. */
export function useBotSpeaking(): boolean {
  const [speaking, setSpeaking] = useState(false)

  useRTVIClientEvent(
    RTVIEvent.BotStartedSpeaking,
    useCallback(() => setSpeaking(true), [])
  )
  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => setSpeaking(false), [])
  )
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => setSpeaking(false), [])
  )

  return speaking
}
