import { SparklesIcon } from "lucide-react";

import { PipecatMark } from "@/components/layout/pipecat-mark";
import {
  type SessionStatus,
  useSessionStatus,
} from "@/hooks/use-session-status";
import { cn } from "@/lib/utils";
import { useEffectsStore } from "@/stores/effects-store";

const TITLE = "Pipecat Expressivity";
const SUBTITLE = "Voice Reader + Tone Reader";
const EFFECTS = "Effects";
const EFFECTS_HINT =
  "The glass pill and the wisps are drawn on the GPU. Turn them off on a device that struggles.";

const STATUS_TEXT: Record<SessionStatus, string> = {
  offline: "Play a clip or speak",
  connecting: "Connecting",
  ready: "Ready",
  hearing: "Listening",
  reading: "Reading",
  failed: "No reading",
};

/** The page's name, and what is happening right now. */
export function AppHeader() {
  const status = useSessionStatus();
  const hasEffects = useEffectsStore((state) => state.hasEffects);
  const toggleEffects = useEffectsStore((state) => state.toggleEffects);
  const isWorking =
    status === "connecting" || status === "hearing" || status === "reading";

  return (
    <header className="flex items-center justify-between gap-x-6 text-xs font-medium tracking-widest whitespace-nowrap text-muted-foreground uppercase">
      <h1 className="flex items-center gap-3">
        <PipecatMark className="size-5 text-foreground" />
        {/* Stacked, the mark stands for the name, which is still read out. */}
        <span className="sr-only text-foreground lg:not-sr-only">{TITLE}</span>
        <span className="sr-only lg:not-sr-only">{SUBTITLE}</span>
      </h1>
      <div className="flex items-center gap-x-6">
        <button
          type="button"
          aria-pressed={hasEffects}
          title={EFFECTS_HINT}
          onClick={toggleEffects}
          className={cn(
            "flex cursor-pointer items-center gap-2 tracking-widest uppercase outline-none hover:text-foreground focus-visible:text-foreground focus-visible:underline",
            hasEffects && "text-foreground",
          )}
        >
          <SparklesIcon aria-hidden="true" className="size-3.5" />
          {EFFECTS} {hasEffects ? "on" : "off"}
        </button>
        <p
          role="status"
          aria-live="polite"
          className={cn(
            "flex items-center gap-2",
            status === "failed" ? "text-destructive" : "text-foreground",
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              "size-2 rounded-full bg-tone-now",
              isWorking && "animate-status motion-reduce:animate-none",
            )}
          />
          {STATUS_TEXT[status]}
        </p>
      </div>
    </header>
  );
}
