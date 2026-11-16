import { useSessionStatus } from "@/hooks/use-session-status";
import { cn } from "@/lib/utils";

const LABEL = "Voice indicator";

/**
 * The pill's stand-in with the effects off: a plain circle in the colour of
 * the turn, drawn with CSS alone. It pulses while a turn is heard or read.
 */
export function SimpleOrb() {
  const status = useSessionStatus();
  const isWorking =
    status === "connecting" || status === "hearing" || status === "reading";
  return (
    <div
      role="img"
      aria-label={LABEL}
      className={cn(
        "absolute inset-1/5 rounded-full border-2 border-tone-now bg-tone-now/15",
        isWorking && "animate-status motion-reduce:animate-none",
      )}
    />
  );
}
