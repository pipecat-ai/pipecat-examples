import type { TransportState } from "@pipecat-ai/client-js"
import {
  PipecatClientProvider,
  usePipecatClientTransportState,
} from "@pipecat-ai/client-react"

import { AudioVisualizerBar } from "@/components/pipecat/audio-visualizer-bar"
import { AudioVisualizerWave } from "@/components/pipecat/audio-visualizer-wave"
import { BotAudioOutput } from "@/components/pipecat/bot-audio"
import { ConnectButton } from "@/components/pipecat/connect-button"
import { Conversation } from "@/components/pipecat/conversation"
import { Metric } from "@/components/pipecat/metric"
import { Panel } from "@/components/pipecat/panel"
import { TextInput } from "@/components/pipecat/text-input"
import { UserAudioControl } from "@/components/pipecat/user-audio-control"
import { usePipecatApp } from "@/hooks/use-pipecat-app"
import {
  usePipecatMetricValue,
  usePipecatTokenTotals,
} from "@/hooks/use-pipecat-metrics"
import { useBotSpeaking, useSessionVersions } from "@/hooks/use-session"
import { useToolCallFlash } from "@/hooks/use-tool-calls"
import { sessionConfig } from "@/lib/session-config"
import { cn } from "@/lib/utils"

/**
 * The model's context window — the denominator the token readout counts
 * against (server/bot.py runs pipecat-ai/phonellm-alpha-1).
 */
const CONTEXT_WINDOW = 1_000_000

/**
 * Retro dither for the agent orb. levels well above the default keeps the
 * quantisation from knocking the dim violet off-hue; alphaLevels 2
 * hard-stipples the edge, so the orb reads as a field of dots. Hoisted
 * because it is compiled into the shader — a fresh object each render
 * would rebuild the WebGL program on every frame.
 */
const ORB_DITHER = { levels: 12, alphaLevels: 2 } as const

/** Processing at or above this many seconds reads as slow, and goes amber. */
const SLOW_PROCESSING_SECONDS = 1

/**
 * The bot's reservation tools (server/tools.py). `name` must match the
 * function name the server reports; `label` is the counter's short form.
 */
const RESERVATION_TOOLS = [
  { name: "get_reservation", label: "get" },
  { name: "create_reservation", label: "create" },
  { name: "update_reservation", label: "update" },
] as const

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/** Seconds → the shortest reading that still says what it is. */
function formatDuration(seconds: number | null): string | null {
  if (seconds === null) return null
  return seconds < 1
    ? `${Math.round(seconds * 1000)}ms`
    : `${seconds.toFixed(1)}s`
}

/** 1500 → "1.5k", 31000 → "31k", 1000000 → "1M". */
function formatTokens(value: number): string {
  const scale = (n: number) =>
    n >= 10 ? String(Math.round(n)) : n.toFixed(1).replace(/\.0$/, "")
  if (value >= 1_000_000) return `${scale(value / 1_000_000)}M`
  if (value >= 1_000) return `${scale(value / 1_000)}k`
  return String(Math.round(value))
}

// ---------------------------------------------------------------------------
// Session phase
// ---------------------------------------------------------------------------

type Phase = "idle" | "starting" | "live" | "error"

const STARTING_STATES: TransportState[] = [
  "initializing",
  "authenticating",
  "authenticated",
  "connecting",
  "disconnecting",
]
const LIVE_STATES: TransportState[] = ["connected", "ready"]

function phaseOf(transportState: TransportState, error: string | null): Phase {
  if (error || transportState === "error") return "error"
  if (LIVE_STATES.includes(transportState)) return "live"
  if (STARTING_STATES.includes(transportState)) return "starting"
  return "idle"
}

// ---------------------------------------------------------------------------
// Readouts
// ---------------------------------------------------------------------------

/** One tool's session call count, flashed green for a beat on each call. */
function ToolCounter({ name, label }: { name: string; label: string }) {
  const { count, flashing } = useToolCallFlash(name)
  return (
    <Metric
      layout="stack"
      label={label}
      value={String(count).padStart(2, "0")}
      // duration-0 in, duration-700 out: the whole cell snaps green with
      // the call and fades back over the beat after it.
      valueClassName={cn(
        "transition-colors duration-700",
        flashing ? "text-active duration-0" : "text-foreground"
      )}
      className={cn(
        "pt-5 pb-3 transition-colors duration-700 not-first:border-l not-first:border-border not-first:pl-3",
        flashing &&
          "bg-active/25 duration-0 [&_[data-slot=metric-label]]:text-active"
      )}
    />
  )
}

function MetricsPanel() {
  const ttfat = usePipecatMetricValue("ttfa")
  const ttfb = usePipecatMetricValue("ttfb")
  const processing = usePipecatMetricValue("processing")
  const { tokens, hasTokens } = usePipecatTokenTotals()

  return (
    <Panel title="metrics">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 px-4 pt-5 pb-2">
        <Metric label="ttfat" value={formatDuration(ttfat)} />
        <Metric label="ttfb" value={formatDuration(ttfb)} />
        <Metric
          label="processing"
          value={formatDuration(processing)}
          valueClassName={
            processing !== null && processing >= SLOW_PROCESSING_SECONDS
              ? "text-tool"
              : undefined
          }
        />
        <Metric
          label="tokens"
          value={
            hasTokens
              ? `${formatTokens(tokens.total)}/${formatTokens(CONTEXT_WINDOW)}`
              : null
          }
        />
      </div>
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Agent panel
// ---------------------------------------------------------------------------

/** Dot and word for the agent panel's status, printed on its top border. */
function AgentStatus({ phase, speaking }: { phase: Phase; speaking: boolean }) {
  const status = {
    idle: { label: "idle", tone: "text-muted-foreground/60" },
    starting: { label: "connecting", tone: "text-tool" },
    live: { label: speaking ? "speaking" : "listening", tone: "text-active" },
    error: { label: "error", tone: "text-inactive" },
  }[phase]

  return (
    <span className="text-muted-foreground">
      <span className={cn("mr-1.5", status.tone)}>●</span>
      {status.label}
    </span>
  )
}

/** The line under the orb: what the session is doing, and what to do next. */
function AgentCaption({ phase, error }: { phase: Phase; error: string | null }) {
  if (phase === "error") {
    return (
      <p className="absolute inset-x-6 bottom-[16%] text-center text-inactive">
        {error ?? "session failed"}
      </p>
    )
  }
  const [prefix, action] = {
    idle: ["not connected — ", "connect to talk to the agent"],
    starting: ["connecting — ", "negotiating the session"],
    live: ["connected — ", "say something, or type below"],
  }[phase]

  return (
    <p className="absolute inset-x-6 bottom-[16%] text-center">
      <span className="text-muted-foreground/70">{prefix}</span>
      <span className="text-foreground">{action}</span>
    </p>
  )
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

function Session({
  onConnect,
  onDisconnect,
  error,
}: {
  onConnect: () => void
  onDisconnect: () => void
  error: string | null
}) {
  const transportState = usePipecatClientTransportState() as TransportState
  const speaking = useBotSpeaking()
  const versions = useSessionVersions()
  const phase = phaseOf(transportState, error)

  const session = {
    idle: { label: "session idle", tone: "text-muted-foreground" },
    starting: { label: "session starting", tone: "text-tool" },
    live: { label: "session live", tone: "text-active" },
    error: { label: "session error", tone: "text-inactive" },
  }[phase]

  return (
    <div className="flex h-svh flex-col gap-4 p-4 text-[13px] leading-[1.6]">
      <header className="flex h-9 shrink-0 items-center justify-between">
        <h1 className="flex items-baseline gap-2 text-base">
          <span className="font-bold">pipecat</span>
          <span className="text-muted-foreground/60">/</span>
          <span className="font-medium text-agent">phonellm</span>
          <span className="text-[13px] text-muted-foreground/70">alpha·1</span>
        </h1>
        <ConnectButton onConnect={onConnect} onDisconnect={onDisconnect} />
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-[1.45fr_1fr] gap-4">
        <Panel
          title="agent"
          status={<AgentStatus phase={phase} speaking={speaking} />}
          footnote="reservation bot · demo"
          className="min-h-0"
        >
          {/* The orb is clipped by this inner box rather than the panel, so
              the panel's legends can still hang over its border. pb-12 rides
              the orb above centre, leaving the caption room underneath. */}
          <div className="relative flex h-full items-center justify-center overflow-hidden pb-12">
            <AudioVisualizerWave
              participantType="bot"
              size={520}
              isConnecting={phase === "starting"}
              // Two fixed tones, held: accentColor pins the pair (so speech
              // can't widen the hue range), and a colorShift this high
              // interleaves them layer by layer — the palette reads as one
              // steady violet-into-blue rather than a cycle through it.
              color="--agent"
              accentColor="--client"
              colorShift={0.4}
              // A calm, even stipple: no specular blob over the hollow, a
              // rounder edge, and dim enough that the dither reads as a dot
              // field rather than a solid mass.
              noHighlight
              amplitude={0.5}
              fill={0.85}
              hollow={0.2}
              core={0.3}
              density={0.32}
              glow={0.55}
              dither={ORB_DITHER}
            />
            {/* Level bars sit in the orb's hollow, at their own scale — the
                orb grew around them, they did not grow with it. */}
            <div className="absolute inset-0 bottom-12 flex items-center justify-center">
              <AudioVisualizerBar
                participantType="bot"
                isConnecting={phase === "starting"}
                barOrigin="center"
                barMaxHeight={96}
                barLineCap="square"
              />
            </div>
          </div>
          <AgentCaption phase={phase} error={error} />
        </Panel>

        <div className="flex min-h-0 flex-col gap-3">
          <Panel title="transcript" className="flex min-h-0 flex-1 flex-col">
            <div className="flex min-h-0 flex-1 flex-col px-4 pt-5 pb-3">
              <Conversation />
              <div className="mt-3 flex items-center gap-2 border-t border-border pt-2.5">
                <TextInput className="flex-1" />
                <UserAudioControl />
              </div>
            </div>
          </Panel>

          <Panel title="tool calls">
            <div className="grid grid-cols-3 px-4">
              {RESERVATION_TOOLS.map((tool) => (
                <ToolCounter
                  key={tool.name}
                  name={tool.name}
                  label={tool.label}
                />
              ))}
            </div>
          </Panel>

          <MetricsPanel />
        </div>
      </main>

      <footer className="flex h-6 shrink-0 items-center justify-between text-[13px] font-medium">
        <span className={session.tone}>
          <span className="mr-1.5">▸▸</span>
          {session.label}
        </span>
        {/* Both versions are session facts: the RTVI one arrives in the
            bot-ready payload, so neither shows until there is a session. */}
        {versions.rtvi && (
          <span className="text-muted-foreground/70">
            rtvi v{versions.rtvi} · pipecat-client-js v{versions.client}
          </span>
        )}
      </footer>

      <BotAudioOutput />
    </div>
  )
}

/**
 * Transport and connect strategy for this build — smallwebrtc against a local
 * bot in dev, Daily via the start endpoint in production. Resolved once at
 * module load: it reads build-time env, and changing transportType rebuilds
 * the client.
 */
const SESSION = sessionConfig()

export function App() {
  const { client, connect, disconnect, error } = usePipecatApp(SESSION)

  if (!client) {
    return (
      <div className="flex h-svh items-center justify-center text-[13px] text-muted-foreground">
        {error ?? "starting client…"}
      </div>
    )
  }

  return (
    <PipecatClientProvider client={client}>
      <Session onConnect={connect} onDisconnect={disconnect} error={error} />
    </PipecatClientProvider>
  )
}

export default App
