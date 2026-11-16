import type { Sincerity } from "@/lib/perception";
import { cn } from "@/lib/utils";

const LABEL = "Sincerity";

interface SincerityBadgeProps {
  /** Whether the model heard the turn as meant, or undefined when there is no reading. */
  sincerity: Sincerity | undefined;
}

/** Whether a model heard the turn as meant, as a small badge: quiet for sincere, lit for sarcastic. */
export function SincerityBadge({ sincerity }: SincerityBadgeProps) {
  if (!sincerity) return null;
  const isSarcastic = sincerity === "sarcastic";
  return (
    <span
      aria-label={`${LABEL}: ${sincerity}`}
      className={cn(
        "flex items-center gap-1 rounded-full border px-1.5 py-1 text-[0.5rem] leading-none font-medium tracking-wider whitespace-nowrap uppercase @[15rem]:gap-1.5 @[15rem]:px-2 @[15rem]:text-gauge-unit @[15rem]:tracking-widest",
        isSarcastic
          ? "border-sarcastic/50 bg-sarcastic/15 text-sarcastic"
          : "border-border bg-card/40 text-foreground",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 rounded-full",
          isSarcastic ? "bg-sarcastic" : "border border-muted-foreground",
        )}
      />
      {sincerity}
    </span>
  );
}
