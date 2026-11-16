import { useElapsed } from "@/hooks/use-elapsed";
import { LATENCY_SCALE_MS } from "@/lib/perception";
import { cn } from "@/lib/utils";

const TITLE = "Latency";
const UNIT = "ms";
const EMPTY = "--";
const DOTS = 40;
/** The dots never reorder, so their position identifies them. */
const INDEXES = Array.from({ length: DOTS }, (_, index) => index);

interface LatencyReadoutProps {
  /** How long the read took, in milliseconds, once it is in. */
  ms: number | undefined;
  /** When the turn stopped, on the page's clock, or null while there is none to count from. */
  stoppedAt: number | null;
  /** Whether the reading is still awaited: the count runs until it lands. */
  isPending: boolean;
}

/**
 * How long a model took over the turn, as a big figure and a row of dots on
 * a scale both models share. While the reading is awaited the figure counts
 * up from the moment the turn stopped, so the wait is seen as it happens.
 */
export function LatencyReadout({
  ms,
  stoppedAt,
  isPending,
}: LatencyReadoutProps) {
  const elapsed = useElapsed(stoppedAt, isPending);
  const shown = isPending ? (elapsed ?? 0) : ms;
  const lit =
    shown === undefined
      ? 0
      : Math.max(1, Math.round(Math.min(shown / LATENCY_SCALE_MS, 1) * DOTS));
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p
        className={cn(
          "flex items-baseline gap-2 leading-none",
          shown === undefined && "opacity-30",
          isPending && "text-muted-foreground",
        )}
      >
        <span className="font-display text-latency leading-none font-black tabular-nums">
          {shown === undefined ? EMPTY : Math.round(shown)}
        </span>
        <span className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
          {UNIT}
          {/* Only where the lane is wide enough for it. */}
          <span className="sr-only @[15rem]:not-sr-only"> {TITLE}</span>
        </span>
      </p>
      <div aria-hidden="true" className="flex justify-between">
        {INDEXES.map((index) => (
          <span
            key={index}
            className={cn(
              "size-1 rounded-full sm:size-1.5",
              index >= lit && "bg-meter-track",
              index < lit && (isPending ? "bg-foreground" : "bg-tone-now"),
            )}
          />
        ))}
      </div>
    </div>
  );
}
