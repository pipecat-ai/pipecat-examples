"use client"

import type { TransportState } from "@pipecat-ai/client-js"
import {
  usePipecatClient,
  usePipecatClientTransportState,
} from "@pipecat-ai/client-react"

import { cn } from "@/lib/utils"

// Tones, not variants: go is green, stop is pink, and the transitional
// states sit in the border grey the rest of the chrome is drawn in.
const GO = "border-active/60 text-active hover:border-active hover:bg-active/10"
const STOP =
  "border-inactive/60 text-inactive hover:border-inactive hover:bg-inactive/10"
const WAIT = "border-border text-muted-foreground"

interface ButtonState {
  label: string
  /** Leading glyph — a play caret to start a session, a stop square to end one. */
  glyph: string
  tone: string
  /** Transitional states are inert until the transport settles. */
  busy?: boolean
}

const STATES: Record<TransportState, ButtonState> = {
  disconnected: { label: "connect", glyph: "▸", tone: GO },
  initializing: { label: "starting", glyph: "·", tone: WAIT, busy: true },
  initialized: { label: "connect", glyph: "▸", tone: GO },
  authenticating: { label: "connecting", glyph: "·", tone: WAIT, busy: true },
  authenticated: { label: "connecting", glyph: "·", tone: WAIT, busy: true },
  connecting: { label: "connecting", glyph: "·", tone: WAIT, busy: true },
  connected: { label: "disconnect", glyph: "▪", tone: STOP },
  ready: { label: "disconnect", glyph: "▪", tone: STOP },
  disconnecting: { label: "closing", glyph: "·", tone: WAIT, busy: true },
  error: { label: "retry", glyph: "▸", tone: GO },
}

/** States where a click ends the session rather than starting one. */
const DISCONNECT_STATES: TransportState[] = ["connected", "ready"]

export interface ConnectButtonProps {
  /** Starts the session. Defaults to client.connect(). */
  onConnect?: () => void
  /** Ends the session. Defaults to client.disconnect(). */
  onDisconnect?: () => void
  className?: string
}

/**
 * The one control that runs the session: a flat, letterspaced button that
 * reads the transport state and swaps label, glyph and tone with it. Pass
 * onConnect when the app owns session startup (an auth endpoint, a bot to
 * start first); without it the button drives the client directly. Must be
 * rendered inside a PipecatClientProvider.
 */
export function ConnectButton({
  onConnect,
  onDisconnect,
  className,
}: ConnectButtonProps) {
  const client = usePipecatClient()
  // client-react's .d.ts types this hook against a TransportState it
  // never imports, so name the client-js one to index STATES with it.
  const transportState = usePipecatClientTransportState() as TransportState
  const state = STATES[transportState]

  const handleClick = () => {
    if (DISCONNECT_STATES.includes(transportState)) {
      if (onDisconnect) return onDisconnect()
      client?.disconnect().catch(() => {})
      return
    }
    if (onConnect) return onConnect()
    // Connection failures surface through the transport's "error" state.
    client?.connect().catch(() => {})
  }

  return (
    <button
      type="button"
      data-state={transportState}
      disabled={state.busy}
      aria-busy={state.busy}
      onClick={handleClick}
      className={cn(
        "flex shrink-0 items-center border px-4 py-2 text-[13px] leading-none tracking-[0.1em] uppercase transition-colors",
        state.tone,
        className
      )}
    >
      <span className="mr-1.5 tracking-normal">{state.glyph}</span>
      {state.label}
    </button>
  )
}
