import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  Panel,
  PanelContent,
  PanelHeader,
  PanelTitle,
  usePipecatEventStream,
  type PipecatEventGroup,
  type PipecatEventLog,
} from "@pipecat-ai/voice-ui-kit";
import { useEffect, useRef, useState } from "react";

const formatTimestamp = (date: Date) => {
  return date.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  });
};

const getEventColor = (type: string) => {
  if (type.includes("error") || type.includes("Error"))
    return "text-destructive";
  if (type.includes("warning") || type.includes("Warning"))
    return "text-warning";
  if (type.includes("bot")) return "text-primary";
  if (type.includes("metrics")) return "text-muted-foreground";
  if (type.includes("user")) return "text-agent";
  if (type.includes("transport")) return "text-warning";
  return "text-primary";
};

type EventStreamRowProps = {
  event: PipecatEventLog;
  eventColorClass: string;
  isFirstInGroup: boolean;
  hasMultiple: boolean;
  onToggle?: () => void;
  formatTimestamp: (date: Date) => string;
};

function EventStreamRow({
  event,
  eventColorClass,
  isFirstInGroup,
  hasMultiple,
  onToggle,
  formatTimestamp,
}: EventStreamRowProps) {
  return (
    <div className="flex items-start hover:bg-primary/5 px-1">
      {hasMultiple && isFirstInGroup ? (
        <span onClick={onToggle} className="mr-2 mt-0.5">
          ▼
        </span>
      ) : (
        <span className="text-border mr-2">│</span>
      )}
      <div className="flex-1 flex items-start gap-2 text-xs">
        <span className="text-primary opacity-50">
          [{formatTimestamp(event.timestamp)}]
        </span>
        <span className={`${eventColorClass} font-bold`}>{event.type}:</span>
        <span className="text-primary opacity-80 break-all">
          {event.data ? JSON.stringify(event.data).slice(0, 100) : "null"}
          {event.data && JSON.stringify(event.data).length > 100 ? "..." : ""}
        </span>
      </div>
    </div>
  );
}

export function EventStreamPanel() {
  const { events, groups } = usePipecatEventStream({
    maxEvents: 500,
    ignoreEvents: [
      RTVIEvent.LocalAudioLevel,
      RTVIEvent.RemoteAudioLevel,
      RTVIEvent.BotTtsText,
      RTVIEvent.BotLlmText,
    ],
    groupConsecutive: true,
  });
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const eventsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  // Use grouped results from hook
  const eventGroups: ReadonlyArray<PipecatEventGroup> = groups;

  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  return (
    <Panel className="h-full">
      <PanelHeader>
        <PanelTitle>
          System Event Monitor
          <span className="terminal-text hidden terminal:static">
            &slash;&slash; RTVI Protocol
          </span>
        </PanelTitle>
        <div className="terminal-text hidden terminal:static">
          Events: {events.length}
        </div>
      </PanelHeader>
      <PanelContent className="text-sm w-full min-h-0 flex-1">
        <div className="overflow-y-auto min-h-0 h-full">
          {events.length === 0 ? (
            <div className="text-center py-8">
              <div className="opacity-50 text-lg mb-2 terminal:uppercase terminal:before:content-['◄'] terminal:before:mr-2 terminal:after:content-['►'] terminal:after:ml-2">
                No Events Recorded
              </div>
              <div className="text-xs opacity-30">
                System events will appear here
              </div>
            </div>
          ) : (
            <div className="space-y-0">
              {eventGroups.map((group) => {
                const isExpanded = expandedGroups.has(group.id);
                const hasMultiple = group.events.length > 1;
                const eventColor = getEventColor(group.type);

                if (!hasMultiple || isExpanded) {
                  return group.events.map((event, index) => (
                    <EventStreamRow
                      key={event.id}
                      event={event}
                      eventColorClass={eventColor}
                      isFirstInGroup={hasMultiple && index === 0}
                      hasMultiple={hasMultiple}
                      onToggle={() => toggleGroup(group.id)}
                      formatTimestamp={formatTimestamp}
                    />
                  ));
                } else {
                  // Show collapsed group
                  return (
                    <div
                      key={group.id}
                      className="flex items-start hover:bg-primary/5 px-1"
                    >
                      <button
                        onClick={() => toggleGroup(group.id)}
                        className="text-primary hover:text-primary/80 mr-2 mt-0.5"
                        style={{ fontSize: "10px" }}
                      >
                        ▶
                      </button>
                      <div className="flex-1 flex items-start gap-2">
                        <span className="text-primary opacity-50">
                          [{formatTimestamp(group.events[0].timestamp)}]
                        </span>
                        <span className={`${eventColor} font-bold`}>
                          {group.type}
                        </span>
                        <span className="text-secondary opacity-60">
                          ({group.events.length} events)
                        </span>
                      </div>
                    </div>
                  );
                }
              })}
              <div ref={eventsEndRef} />
            </div>
          )}
        </div>
      </PanelContent>
    </Panel>
  );
}
