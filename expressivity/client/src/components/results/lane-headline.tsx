import type { ReactNode } from "react";

const EMPTY = "--";

interface LaneHeadlineProps {
  /** What the word answers, such as "Tone". */
  title: string;
  /** The word, or undefined when there is no reading. */
  word: string | undefined;
  /** Something small that goes with the word, shown at the far end of its title's line. */
  badge?: ReactNode;
  /** The word's colour. */
  colorClassName: string;
}

/** One word of what a model heard, as a headline of its lane. It is shown whole the moment there is one: nothing on a lane is eased in, as when a reading lands is what the page is about. */
export function LaneHeadline({
  title,
  word,
  badge,
  colorClassName,
}: LaneHeadlineProps) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      {/* As tall as a badge whether or not there is one, so one landing moves nothing. */}
      <div className="flex h-6 items-center justify-between gap-2">
        <span className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
          {title}
        </span>
        {badge}
      </div>
      <h3
        aria-label={word ? `${title}: ${word}` : undefined}
        className="font-display text-lane-headline leading-none font-black tracking-tight uppercase"
      >
        {/* The size above is kept apart from the colour here: merged in one cn(), it would be taken for a colour and dropped. */}
        <span
          aria-hidden={word ? "true" : undefined}
          className={`flex ${word ? colorClassName : "opacity-30"}`}
        >
          {word ?? EMPTY}
        </span>
      </h3>
    </div>
  );
}
