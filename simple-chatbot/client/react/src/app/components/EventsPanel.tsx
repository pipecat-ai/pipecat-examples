"use client";

import type {
  BotOutputData,
  Participant,
  RTVIMessage,
} from "@pipecat-ai/client-js";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { FilterIcon } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState } from "react";

import {
  usePipecatEventStream,
  type PipecatEventLog,
} from "@/hooks/use-pipecat-event-stream";
import { Button } from "@/components/ui/button";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";

import { Panel, PanelHeader, PanelTitle } from "./Panel";

const MAX_DESCRIPTION = 200;

// The shared store trims to its cap before per-subscriber filters run, and
// Daily emits remoteAudioLevel about ten times a second, so a 500-event cap
// evicts the rows this panel exists to show within a minute. Raise it well
// past the noise. (The upstream fix is adding those types to the hook's
// capture ignore list; the vendored hook is left untouched.)
const MAX_EVENTS = 5000;

/** High-frequency events hidden from this panel. */
const HIDDEN_EVENTS: string[] = [
  RTVIEvent.RemoteAudioLevel,
  RTVIEvent.BotTtsText,
  RTVIEvent.BotLlmText,
];

function stringify(value: unknown): string {
  try {
    return typeof value === "string" ? value : (JSON.stringify(value) ?? "");
  } catch {
    return String(value);
  }
}

function truncate(text: string): string {
  return text.length > MAX_DESCRIPTION
    ? `${text.slice(0, MAX_DESCRIPTION)}…`
    : text;
}

/** SmallWebRTC reports remote tracks without a participant; those are the bot's. */
function participantLabel(participant?: Participant): string {
  if (!participant) return "bot";
  return participant.local ? "local" : participant.id;
}

/** One-line summary per event, in the spirit of the voice-ui-kit events panel. */
function describeEvent({ type, data }: PipecatEventLog): string {
  const record = (data ?? {}) as Record<string, unknown>;
  switch (type) {
    case RTVIEvent.TransportStateChanged:
      return `Transport state changed: ${String(data)}`;
    case RTVIEvent.Connected:
      return "Client connected";
    case RTVIEvent.Disconnected:
      return "Client disconnected";
    case RTVIEvent.BotConnected:
      return `Bot connected: ${String(record.id ?? "")}`;
    case RTVIEvent.BotDisconnected:
      return `Bot disconnected: ${String(record.id ?? "")}`;
    case RTVIEvent.BotReady:
      return `Bot ready (v${String(record.version ?? "?")}): ${truncate(stringify(record.about ?? {}))}`;
    case RTVIEvent.BotStartedSpeaking:
      return "Bot started speaking";
    case RTVIEvent.BotStoppedSpeaking:
      return "Bot stopped speaking";
    case RTVIEvent.UserStartedSpeaking:
      return "User started speaking";
    case RTVIEvent.UserStoppedSpeaking:
      return "User stopped speaking";
    case RTVIEvent.UserTranscript:
      return `${record.final ? "Final" : "Interim"} transcript: ${String(record.text ?? "")}`;
    case RTVIEvent.BotOutput: {
      const output = data as BotOutputData;
      const details = [
        output.aggregated_by,
        output.segment_id !== undefined ? `#${output.segment_id}` : null,
        output.spoken_status
          ? `spoken: ${output.spoken_status}`
          : output.will_be_spoken === false
            ? "not spoken"
            : null,
      ].filter(Boolean);
      return `Bot output (${details.join(", ")}): ${output.text}`;
    }
    case RTVIEvent.BotTranscript:
      return String(record.text ?? truncate(stringify(data)));
    case RTVIEvent.TrackStarted:
    case RTVIEvent.TrackStopped: {
      const [track, participant] = (
        Array.isArray(data) ? data : [data]
      ) as [MediaStreamTrack | undefined, Participant | undefined];
      const verb = type === RTVIEvent.TrackStarted ? "started" : "stopped";
      return `Track ${verb}: ${track?.kind ?? "media"} for participant ${participantLabel(participant)}`;
    }
    case RTVIEvent.ParticipantConnected:
      return `Participant connected: ${String(record.id ?? "")}`;
    case RTVIEvent.ParticipantLeft:
      return `Participant left: ${String(record.id ?? "")}`;
    case RTVIEvent.ServerMessage:
      return `Server message: ${truncate(stringify(data))}`;
    case RTVIEvent.Error:
    case RTVIEvent.MessageError: {
      const message = (data ?? {}) as Partial<RTVIMessage>;
      const payload = message.data as { error?: string } | undefined;
      return `Error: ${payload?.error ?? truncate(stringify(data))}`;
    }
    case RTVIEvent.MicUpdated:
    case RTVIEvent.CamUpdated:
    case RTVIEvent.SpeakerUpdated:
      return `Selected: ${String(record.label || record.deviceId || "none")}`;
    case RTVIEvent.AvailableMicsUpdated:
    case RTVIEvent.AvailableCamsUpdated:
    case RTVIEvent.AvailableSpeakersUpdated: {
      const devices = Array.isArray(data) ? (data as { label?: string }[]) : [];
      return `${devices.length} available: ${devices.map((d) => d.label || "unnamed").join(", ")}`;
    }
    case RTVIEvent.MediaStateUpdated: {
      const states = data as Record<string, { state?: string }>;
      return Object.entries(states)
        .map(([kind, value]) => `${kind}: ${String(value?.state ?? "?")}`)
        .join(", ");
    }
    default:
      return data === undefined ? "" : truncate(stringify(data));
  }
}

/**
 * botOutput re-emits as spoken progress advances; collapse consecutive
 * events for the same segment and status into one row. Every other event
 * keeps its own row.
 */
function groupKey(event: PipecatEventLog): string {
  if (event.type !== RTVIEvent.BotOutput) return event.id;
  const { segment_id, spoken_status } = event.data as BotOutputData;
  return `${event.type}:${String(segment_id)}:${String(spoken_status)}`;
}

interface Row {
  id: string;
  time: string;
  type: string;
  description: string;
  /** Untruncated payload, shown on hover. */
  title: string;
}

function toRow(event: PipecatEventLog): Row {
  return {
    id: event.id,
    time: event.timestamp.toLocaleTimeString(),
    type: event.type,
    description: describeEvent(event),
    title: stringify(event.data),
  };
}

const EventRow = memo(function EventRow({ row }: { row: Row }) {
  return (
    <div className="contents">
      <span className="text-muted-foreground">{row.time}</span>
      <span className="font-semibold">{row.type}</span>
      <span className="min-w-0 truncate" title={row.title}>
        {row.description}
      </span>
    </div>
  );
});

interface EventsPanelProps {
  className?: string;
  /** Changing this clears the log, e.g. when the transport is switched. */
  resetKey?: unknown;
}

export function EventsPanel({ className, resetKey }: EventsPanelProps) {
  const [filter, setFilter] = useState("");
  const { groups, paused, setPaused, clear } = usePipecatEventStream({
    maxEvents: MAX_EVENTS,
    ignoreEvents: HIDDEN_EVENTS,
    groupConsecutive: true,
    groupKey,
  });

  // Rows are derived once per event and reused across store flushes.
  const rowCache = useRef(new Map<string, Row>());
  const rows = useMemo(() => {
    const cache = rowCache.current;
    if (cache.size > MAX_EVENTS * 2) cache.clear();
    return groups.map((group) => {
      const first = group.events[0]!;
      let row = cache.get(first.id);
      if (!row) {
        row = toRow(first);
        cache.set(first.id, row);
      }
      return row;
    });
  }, [groups]);

  const query = filter.trim().toLowerCase();
  const visible = query
    ? rows.filter(
        (row) =>
          row.type.toLowerCase().includes(query) ||
          row.description.toLowerCase().includes(query),
      )
    : rows;

  // A new session on the same client clears the log automatically; a
  // rebuilt client (transport switch) does not, so clear on resetKey.
  const firstResetRef = useRef(true);
  useEffect(() => {
    if (firstResetRef.current) {
      firstResetRef.current = false;
      return;
    }
    clear();
  }, [resetKey, clear]);

  // Follow the newest event unless the user has scrolled up to read.
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [visible]);

  const handleClear = () => {
    stickToBottomRef.current = true;
    rowCache.current.clear();
    clear();
  };

  return (
    <Panel aria-label="Events" className={className}>
      <PanelHeader className="justify-between p-2">
        <div className="flex items-center gap-4">
          <PanelTitle>Events</PanelTitle>
          <InputGroup className="h-8 w-48">
            <InputGroupAddon>
              <FilterIcon />
            </InputGroupAddon>
            <InputGroupInput
              placeholder="Filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Filter events"
            />
          </InputGroup>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="xs" onClick={() => setPaused(!paused)}>
            {paused ? "Resume" : "Pause"}
          </Button>
          <Button variant="ghost" size="xs" onClick={handleClear}>
            Clear
          </Button>
        </div>
      </PanelHeader>
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottomRef.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 8;
        }}
        className="min-h-0 flex-1 overflow-auto p-3"
      >
        {visible.length === 0 ? (
          <p className="font-mono text-xs text-muted-foreground">
            {query ? "No events match the filter." : "Waiting for events…"}
          </p>
        ) : (
          <div className="grid grid-cols-[max-content_max-content_1fr] items-baseline gap-x-4 gap-y-1 font-mono text-xs">
            {visible.map((row) => (
              <EventRow key={row.id} row={row} />
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}
