import type { UserPerceptionLabel } from "@pipecat-ai/client-js";

import { percent, type Tone, toneOf } from "@/lib/perception";
import { cn } from "@/lib/utils";

const EMPTY = "--";
const COLUMNS = 8;
const ROWS = 4;
const DOTS = COLUMNS * ROWS;
/** A reading has its model's two likeliest labels, so a lane has two panels. */
const PANELS = [0, 1];

/** Each colour's lit dots, and its panel when it is the likeliest. */
const TONE_STYLES: Record<Tone, { dot: string; top: string }> = {
  positive: {
    dot: "bg-tone-positive",
    top: "border-tone-positive/45 bg-tone-positive/10",
  },
  neutral: {
    dot: "bg-tone-neutral",
    top: "border-tone-neutral/45 bg-tone-neutral/10",
  },
  sad: {
    dot: "bg-tone-sad",
    top: "border-tone-sad/45 bg-tone-sad/10",
  },
  frustrated: {
    dot: "bg-tone-frustrated",
    top: "border-tone-frustrated/45 bg-tone-frustrated/10",
  },
};

/** The grid's dots in the order they're drawn, each with its place in the order they light: bottom row first. */
const GRID = Array.from({ length: DOTS }, (_, drawn) => {
  const row = Math.floor(drawn / COLUMNS);
  return (ROWS - 1 - row) * COLUMNS + (drawn % COLUMNS);
});

/** The one row of dots a panel has where there is no room for the grid. */
const ROW = Array.from({ length: COLUMNS }, (_, index) => index);

interface FeelingPanelsProps {
  /** What the labels answer, such as "Tone". */
  title: string;
  /** The model's likeliest labels, likeliest first, or undefined when there is no reading. */
  feelings: UserPerceptionLabel[] | undefined;
}

/** A panel for each of a model's two likeliest labels: how likely it made it, as a figure and a grid of dots that fills from the bottom. */
export function FeelingPanels({ title, feelings }: FeelingPanelsProps) {
  return (
    <ul className="grid grid-cols-2 gap-2 lg:gap-panel">
      {PANELS.map((place) => {
        const feeling = feelings?.[place];
        const confidence = feeling?.confidence;
        const styles = TONE_STYLES[toneOf(feeling?.label) ?? "neutral"];
        const lit =
          confidence === undefined
            ? 0
            : Math.max(confidence > 0 ? 1 : 0, Math.round(confidence * DOTS));
        const litInRow =
          confidence === undefined
            ? 0
            : Math.max(
                confidence > 0 ? 1 : 0,
                Math.round(confidence * COLUMNS),
              );
        const isTop = place === 0 && feeling !== undefined;
        const value = confidence === undefined ? null : percent(confidence);
        return (
          <li
            // A panel is a place, the likeliest or the next, whatever label holds it.
            key={place}
            className={cn(
              // The name on a line of its own, then the figure and the dots side by side. On a larger
              // screen a panel has more room inside, counted in the screen's height like everything else.
              "flex min-w-0 flex-col gap-1.5 rounded-xl border px-1.5 py-2 lg:rounded-2xl @[17rem]:px-2 lg:@[17rem]:gap-panel lg:@[17rem]:p-panel",
              isTop ? styles.top : "border-border bg-card/40",
            )}
          >
            <span
              className={cn(
                "truncate text-gauge-unit leading-none font-medium tracking-normal uppercase @[17rem]:tracking-wider",
                !feeling && "opacity-30",
              )}
            >
              {feeling?.label ?? EMPTY}
            </span>
            {/* Side by side where the lane is wide enough for a grid of dots; stacked, with one row of dots, where it isn't. */}
            <div
              role="meter"
              aria-label={feeling ? `${title}: ${feeling.label}` : title}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round((confidence ?? 0) * 100)}
              aria-valuetext={value ?? undefined}
              className="flex flex-col gap-1.5 @[17rem]:flex-row @[17rem]:items-center @[17rem]:justify-between @[17rem]:gap-2"
            >
              <span
                className={cn(
                  // As wide as "100%", whatever it reads, so the dots beside it never resize.
                  "w-[4ch] shrink-0 font-display text-panel leading-none font-black whitespace-nowrap",
                  !isTop && "opacity-55",
                )}
              >
                {value ?? EMPTY}
              </span>
              <div className="flex justify-between @[17rem]:hidden">
                {ROW.map((index) => (
                  <span
                    key={index}
                    className={cn(
                      "size-1 rounded-full",
                      index < litInRow ? styles.dot : "bg-meter-track",
                      index < litInRow && !isTop && "opacity-45",
                    )}
                  />
                ))}
              </div>
              <div className="hidden max-w-dotgrid min-w-0 flex-1 grid-cols-8 gap-0.5 lg:gap-1 @[17rem]:grid">
                {GRID.map((order) => (
                  <span
                    key={order}
                    className={cn(
                      "aspect-square rounded-full",
                      order < lit ? styles.dot : "bg-meter-track",
                      order < lit && !isTop && "opacity-45",
                    )}
                  />
                ))}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
