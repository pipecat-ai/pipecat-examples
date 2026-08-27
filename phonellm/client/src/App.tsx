import type { ReactNode } from "react"

import {
  PipecatClientProvider,
  usePipecatClientTransportState,
  type FunctionCallData,
} from "@pipecat-ai/client-react"

import { AudioVisualizerBar } from "@/components/pipecat/audio-visualizer-bar"
import { AudioVisualizerWave } from "@/components/pipecat/audio-visualizer-wave"
import { BotAudioOutput } from "@/components/pipecat/bot-audio"
import { ConnectButton } from "@/components/pipecat/connect-button"
import { Conversation } from "@/components/pipecat/conversation"
import { Metric } from "@/components/pipecat/metric"
import { TextInput } from "@/components/pipecat/text-input"
import { UserAudioControl } from "@/components/pipecat/user-audio-control"
import { usePipecatApp } from "@/hooks/use-pipecat-app"
import {
  usePipecatMetricValue,
  usePipecatTokenTotals,
} from "@/hooks/use-pipecat-metrics"

/** The WebRTC offer endpoint; the Vite dev proxy maps /api to the bot. */
const OFFER_URL = import.meta.env.VITE_OFFER_URL ?? "/api/offer"

const toMs = (seconds: number | null) =>
  seconds === null ? null : seconds * 1000

const formatToolResult = (result: unknown) =>
  typeof result === "string" ? result : JSON.stringify(result, null, 2)

/** Transcript row for a tool call: name, status, and the output as code. */
function ToolCall({ call }: { call: FunctionCallData }) {
  const pending = call.status !== "completed" && !call.cancelled
  return (
    <div className="flex flex-col gap-1 font-mono text-xs">
      <div className="text-muted-foreground">
        <span className="font-semibold text-foreground">
          {call.function_name ?? "tool"}
        </span>
        {pending && " · running…"}
        {call.cancelled && " · cancelled"}
      </div>
      {call.result !== undefined && (
        <pre className="overflow-x-auto bg-muted/50 p-2 text-[11px] leading-relaxed break-all whitespace-pre-wrap">
          {formatToolResult(call.result)}
        </pre>
      )}
    </div>
  )
}

function MetricCell({ children }: { children: ReactNode }) {
  return <div className="bg-background p-4">{children}</div>
}

/** 2x2 grid of latency tiles (seconds → ms) plus session token totals. */
function MetricsGrid() {
  const ttfat = usePipecatMetricValue("ttfa")
  const ttfb = usePipecatMetricValue("ttfb")
  const processing = usePipecatMetricValue("processing")
  const { tokens, hasTokens } = usePipecatTokenTotals()

  // gap-px over the border token paints the internal x/y dividers of the
  // grid without any outer chrome.
  return (
    <div className="grid grid-cols-2 gap-px bg-border [&_[data-slot=metric-value]]:font-mono">
      <MetricCell>
        <Metric label="TTFAT" value={toMs(ttfat)} unit="ms" />
      </MetricCell>
      <MetricCell>
        <Metric label="TTFB" value={toMs(ttfb)} unit="ms" />
      </MetricCell>
      <MetricCell>
        <Metric label="Processing" value={toMs(processing)} unit="ms" />
      </MetricCell>
      <MetricCell>
        <Metric label="Tokens" value={hasTokens ? tokens.total : null} />
      </MetricCell>
    </div>
  )
}

function Session({
  onConnect,
  onDisconnect,
  error,
}: {
  onConnect: () => void
  onDisconnect: () => void
  error: string | null
}) {
  const transportState = usePipecatClientTransportState()
  const isConnecting =
    transportState === "authenticating" ||
    transportState === "authenticated" ||
    transportState === "connecting"

  return (
    <div className="flex h-svh flex-col">
      <header className="flex items-stretch border-b">
        <h1 className="flex shrink-0 items-center px-6 text-sm font-semibold tracking-tight">
          Pipecat PhoneLLM{" "}
          <span className="ml-1.5 font-mono font-normal text-muted-foreground">
            Alpha 1
          </span>
        </h1>
        <ConnectButton
          onConnect={onConnect}
          onDisconnect={onDisconnect}
          className="ml-auto h-auto min-h-11 self-stretch px-8"
        />
      </header>

      <main className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-[2] flex-col items-center justify-center gap-10 p-6">
          <div className="relative flex items-center justify-center">
            <AudioVisualizerWave
              participantType="bot"
              size={640}
              isConnecting={isConnecting}
              className="max-w-full"
            />
            <div className="absolute inset-0 flex items-center justify-center">
              <AudioVisualizerBar
                participantType="bot"
                isConnecting={isConnecting}
                barOrigin="center"
                barMaxHeight={96}
                barLineCap="square"
              />
            </div>
          </div>
          <UserAudioControl
            defaultMode="toggle"
            size="lg"
            visualizerProps={{ barLineCap: "square" }}
          />
          {error && (
            <p className="max-w-md text-center text-sm text-destructive">
              {error}
            </p>
          )}
        </section>

        <aside className="flex w-1/3 min-w-80 flex-col border-l">
          <div className="border-b px-4 py-2 font-mono text-xs tracking-wider text-muted-foreground uppercase">
            Transcript
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <Conversation
              functionCallRenderer={(call) => <ToolCall call={call} />}
              className="min-h-0 flex-1"
            />
            <div className="border-t">
              <TextInput
                buttonContent="Send"
                buttonProps={{
                  variant: "default",
                  className: "h-full px-6",
                }}
                // Flat, full-bleed composer: no border, background, focus
                // ring, or padding on the group; the addon stretches so the
                // send button can fill the row's height.
                className="h-12 border-0 bg-transparent has-[[data-slot=input-group-control]:focus-visible]:ring-0 dark:bg-transparent [&>[data-align=inline-end]]:mr-0 [&>[data-align=inline-end]]:self-stretch [&>[data-align=inline-end]]:py-0 [&>[data-align=inline-end]]:pr-0 [&>input]:px-4"
              />
            </div>
          </div>
          <div className="border-y px-4 py-2 font-mono text-xs tracking-wider text-muted-foreground uppercase">
            Metrics
          </div>
          <MetricsGrid />
        </aside>
      </main>

      <BotAudioOutput />
    </div>
  )
}

export function App() {
  const { client, connect, disconnect, error } = usePipecatApp({
    transportType: "smallwebrtc",
    connectParams: { connectionUrl: OFFER_URL },
  })

  if (!client) {
    return (
      <div className="flex h-svh items-center justify-center text-sm text-muted-foreground">
        {error ?? "Starting client…"}
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
