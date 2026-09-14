"use client";

import { RTVIEvent } from "@pipecat-ai/client-js";
import { FilterIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

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

function compact(value: unknown) {
  let text: string;
  try {
    text = typeof value === "string" ? value : (JSON.stringify(value) ?? "");
  } catch {
    text = String(value);
  }
  return text.length > MAX_DESCRIPTION
    ? `${text.slice(0, MAX_DESCRIPTION)}…`
    : text;
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
      return `Bot ready (v${String(record.version ?? "?")}): ${compact(record.about ?? {})}`;
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
      const details = [
        record.aggregated_by,
        record.segment_id !== undefined ? `#${String(record.segment_id)}` : null,
        record.spoken !== undefined ? `spoken: ${String(record.spoken)}` : null,
      ].filter(Boolean);
      return `Bot output (${details.join(", ")}): ${String(record.text ?? "")}`;
    }
    case RTVIEvent.BotTtsText:
    case RTVIEvent.BotLlmText:
    case RTVIEvent.BotTranscript:
      return String(record.text ?? compact(data));
    case RTVIEvent.TrackStarted:
    case RTVIEvent.TrackStopped: {
      const [track, participant] = Array.isArray(data) ? data : [data];
      const kind = (track as MediaStreamTrack | undefined)?.kind ?? "media";
      const id = (participant as { id?: string } | undefined)?.id ?? "local";
      return `Track ${type === RTVIEvent.TrackStarted ? "started" : "stopped"}: ${kind} for participant ${id}`;
    }
    case RTVIEvent.ParticipantConnected:
      return `Participant connected: ${String(record.id ?? "")}`;
    case RTVIEvent.ParticipantLeft:
      return `Participant left: ${String(record.id ?? "")}`;
    case RTVIEvent.ServerMessage:
      return `Server message: ${compact(data)}`;
    case RTVIEvent.Error:
    case RTVIEvent.MessageError:
      return `Error: ${compact(data)}`;
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
      return data === undefined ? "" : compact(data);
  }
}

export function EventsPanel({ className }: { className?: string }) {
  const [filter, setFilter] = useState("");
  // Audio levels and per-word text events fire continuously and would
  // drown out everything else; botOutput already carries the spoken text.
  const { events, paused, setPaused, clear } = usePipecatEventStream({
    ignoreEvents: [
      RTVIEvent.RemoteAudioLevel,
      RTVIEvent.BotTtsText,
      RTVIEvent.BotLlmText,
    ],
  });

  const query = filter.trim().toLowerCase();
  const visible = query
    ? events.filter((event) => event.type.toLowerCase().includes(query))
    : events;

  // Follow the newest event unless the user has scrolled up to read.
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [visible]);

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
              aria-label="Filter events by type"
            />
          </InputGroup>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="xs" onClick={() => setPaused(!paused)}>
            {paused ? "Resume" : "Pause"}
          </Button>
          <Button variant="ghost" size="xs" onClick={clear}>
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
            {visible.map((event) => (
              <div key={event.id} className="contents">
                <span className="text-muted-foreground">
                  {event.timestamp.toLocaleTimeString()}
                </span>
                <span className="font-semibold">{event.type}</span>
                <span className="min-w-0 truncate" title={compact(event.data)}>
                  {describeEvent(event)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}
