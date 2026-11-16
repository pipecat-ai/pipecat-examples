import { SincerityBadge } from "@/components/results/sincerity-badge";
import {
  labelsOf,
  OVERALL,
  percent,
  sincerityOf,
  toneOf,
} from "@/lib/perception";
import { cn } from "@/lib/utils";
import { usePerceptionStore } from "@/stores/perception-store";

const LABEL = "Overall";
const SARCASM = "Sarcasm";
const EMPTY = "--";

/**
 * What the two readings add up to: the feeling and the sarcasm the bot
 * concludes from the voice and the words together (server/conclusion.py).
 * It spans both cards, as it's made from both, and takes the feeling's colour.
 */
export function Conclusion() {
  const overall = usePerceptionStore((state) => state.overall ?? undefined);
  const feeling = labelsOf(overall, OVERALL.feeling)?.[0];
  const sincerity = sincerityOf(overall, OVERALL.sarcasm);

  return (
    <section
      aria-label={LABEL}
      aria-live="polite"
      data-tone={toneOf(feeling?.label) ?? "neutral"}
      // As tall with a conclusion as without one, and every part of it keeps its place and its
      // width, so nothing moves when one lands.
      className="tone-scope tone-scope-instant @container lane-card flex h-conclusion items-center justify-between gap-4 rounded-2xl border px-3 lg:rounded-3xl lg:px-card"
    >
      <div className="flex min-w-0 items-center gap-3">
        <h2 className="text-xs leading-none font-medium tracking-widest text-muted-foreground uppercase">
          {LABEL}
        </h2>
        <p
          aria-label={feeling ? `${LABEL}: ${feeling.label}` : undefined}
          className={cn(
            "truncate font-display text-conclusion leading-none font-black tracking-tight uppercase",
            feeling ? "text-tone-now" : "opacity-30",
          )}
        >
          {feeling?.label ?? EMPTY}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="flex items-center gap-2 text-xs leading-none font-medium tracking-widest whitespace-nowrap text-muted-foreground uppercase">
          {/* On a phone the badge says it alone. */}
          <span className="sr-only sm:not-sr-only">{SARCASM}</span>
          {/* As wide as "100%", whatever it reads. */}
          <span
            className={cn(
              "w-[4ch] text-right text-foreground tabular-nums",
              !sincerity && "opacity-30",
            )}
          >
            {sincerity ? percent(sincerity.sarcasm) : EMPTY}
          </span>
        </span>
        {/* The badge's place is kept at its widest, "sarcastic", while there is none to show. */}
        <span className="grid justify-items-end">
          <span
            aria-hidden="true"
            className="invisible col-start-1 row-start-1"
          >
            <SincerityBadge sincerity="sarcastic" />
          </span>
          <span className="col-start-1 row-start-1">
            <SincerityBadge sincerity={sincerity?.sincerity} />
          </span>
        </span>
      </div>
    </section>
  );
}
