"use client"

import type {
  LLMFunctionCallStartedData,
  PipecatClient,
} from "@pipecat-ai/client-js"
import { RTVIEvent } from "@pipecat-ai/client-js"
import { usePipecatClient } from "@pipecat-ai/client-react"
import { useEffect, useRef, useState } from "react"
import { create } from "zustand"

import chimeUrl from "@/assets/chime.wav"

interface ToolCallsState {
  /** Per-session call count, keyed by function name. */
  counts: Record<string, number>
  /** Records one call of `name`. */
  record: (name: string) => void
  /** Clears every count (called when a new session connects). */
  reset: () => void
}

/**
 * Module-level store of tool-call counts for the current session. One
 * listener per client feeds it (see useAttachToolCallListeners); any number
 * of tiles subscribe, so counts survive unmounts and late-mounted
 * subscribers see the session's totals. Resets when a new session connects.
 *
 * Counting is driven by the server's `llm-function-call-started` event, so
 * the bot's RTVI observer must report at least the function name — see
 * `RTVIFunctionCallReportLevel` in server/bot.py. Nameless events (report
 * level "none") are ignored.
 */
export const useToolCallsStore = create<ToolCallsState>()((set) => ({
  counts: {},
  record: (name) =>
    set((state) => ({
      counts: { ...state.counts, [name]: (state.counts[name] ?? 0) + 1 },
    })),
  reset: () => set({ counts: {} }),
}))

// ---------------------------------------------------------------------------
// Listener attachment: ref-counted per client so any number of subscribers
// share one RTVI listener, attached by the first and detached by the last.
// ---------------------------------------------------------------------------

const listenerRefCounts = new Map<PipecatClient, number>()

/**
 * Under the bot's voice, not over it — the chime marks a tool firing
 * without competing with whatever the agent is saying at the time.
 */
const CHIME_VOLUME = 0.4

/**
 * Sounds the tool-call chime. A fresh element per call so back-to-back
 * calls overlap rather than cutting each other off, and a silent catch
 * because playback the browser blocks (no user gesture yet) is not worth
 * an error — the counters still tell the story.
 */
function playChime() {
  const chime = new Audio(chimeUrl)
  chime.volume = CHIME_VOLUME
  void chime.play().catch(() => {})
}

function handleFunctionCallStarted(data: LLMFunctionCallStartedData) {
  if (!data.function_name) return
  useToolCallsStore.getState().record(data.function_name)
  playChime()
}

function handleConnected() {
  useToolCallsStore.getState().reset()
}

function attachListeners(client: PipecatClient) {
  const count = listenerRefCounts.get(client) ?? 0
  listenerRefCounts.set(client, count + 1)
  if (count > 0) return
  client.on(RTVIEvent.LLMFunctionCallStarted, handleFunctionCallStarted)
  client.on(RTVIEvent.Connected, handleConnected)
}

function detachListeners(client: PipecatClient) {
  const count = listenerRefCounts.get(client) ?? 0
  if (count <= 1) {
    listenerRefCounts.delete(client)
    client.off(RTVIEvent.LLMFunctionCallStarted, handleFunctionCallStarted)
    client.off(RTVIEvent.Connected, handleConnected)
    return
  }
  listenerRefCounts.set(client, count - 1)
}

/** Shared by every public hook: feed the store from the context client. */
function useAttachToolCallListeners() {
  const client = usePipecatClient()
  useEffect(() => {
    if (!client) return
    attachListeners(client)
    return () => detachListeners(client)
  }, [client])
}

// ---------------------------------------------------------------------------
// Public hooks
// ---------------------------------------------------------------------------

/**
 * How many times `name` has been called this session. Must be rendered
 * inside a PipecatClientProvider.
 */
export function useToolCallCount(name: string): number {
  useAttachToolCallListeners()
  return useToolCallsStore((state) => state.counts[name] ?? 0)
}

export interface UseToolCallFlashReturn {
  /** Calls of this tool so far this session. */
  count: number
  /** True for `durationMs` after each new call — drive the highlight with it. */
  flashing: boolean
}

/**
 * Session call count for `name` plus a momentary `flashing` pulse on each
 * new call. Only increments flash, so the reset at the start of a session
 * stays silent. Must be rendered inside a PipecatClientProvider.
 */
export function useToolCallFlash(
  name: string,
  durationMs = 600
): UseToolCallFlashReturn {
  const count = useToolCallCount(name)
  const [flashing, setFlashing] = useState(false)
  const previousCount = useRef(count)

  useEffect(() => {
    const increased = count > previousCount.current
    previousCount.current = count
    if (!increased) return
    setFlashing(true)
    // Restarts on a rapid second call, so back-to-back calls read as one
    // sustained highlight rather than a dropped flash.
    const timer = setTimeout(() => setFlashing(false), durationMs)
    return () => clearTimeout(timer)
  }, [count, durationMs])

  return { count, flashing }
}
