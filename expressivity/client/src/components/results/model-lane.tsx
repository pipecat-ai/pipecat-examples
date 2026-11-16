import { useEffect, useRef } from "react";

import { LatencyReadout } from "@/components/results/latency-readout";
import { DotGauge } from "@/components/results/dot-gauge";
import { LaneHeadline } from "@/components/results/lane-headline";
import { SincerityBadge } from "@/components/results/sincerity-badge";
import { FeelingPanels } from "@/components/results/feeling-panels";
import { useSincerity } from "@/hooks/use-sincerity";
import { feelingsOf, MODEL_INFO, toneOf, valueOf } from "@/lib/perception";
import { cn } from "@/lib/utils";
import { usePerceptionStore } from "@/stores/perception-store";
import type { Model } from "@/types/perception";

const NO_READING = "No reading";
/** The word over a lane while its turn is heard, and while its model reads it, each with its own pulse. */
const HEARING = { word: "Listening", pulse: "animate-word-hearing" };
const READING = { word: "Reading", pulse: "animate-word-assessing" };
/** The card's jolt as its reading lands: it starts a little large and snaps back. */
const JOLT: Keyframe[] = [
  { transform: "scale(1.035)" },
  { transform: "scale(0.995)", offset: 0.55 },
  { transform: "scale(1)" },
];
const JOLT_MS = 320;

interface ModelLaneProps {
  model: Model;
}

/**
 * One model's side of the page: how long it took over the turn on show, and
 * what it made of it. The lane takes the colour of what its own model read,
 * so a voice and words that differ are told apart at a glance.
 */
export function ModelLane({ model }: ModelLaneProps) {
  const info = MODEL_INFO[model];
  const reading = usePerceptionStore((state) => state.readings[model]);
  const readMs = usePerceptionStore((state) => state.readMs[model]);
  const hasMissed = usePerceptionStore((state) => state.missed[model]);
  const phase = usePerceptionStore((state) => state.phase);
  const stoppedAt = usePerceptionStore((state) => state.stoppedAt);

  const isHearing = phase === "hearing";
  const isPending = phase === "reading" && !reading && !hasMissed;
  const working = isHearing ? HEARING : isPending ? READING : null;
  const signals = reading?.signals;
  const feelings = feelingsOf(signals, model);
  const likeliest = feelings?.[0]?.label;
  const sincerity = useSincerity(model);

  // The card itself, for its jolt. It can't be drawn afresh for each reading as its flash is:
  // the orb's wisps hold on to it (energy-wisps.tsx).
  const card = useRef<HTMLElement>(null);
  const landedAt = reading?.arrivedMs;
  useEffect(() => {
    if (landedAt === undefined) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    card.current?.animate(JOLT, { duration: JOLT_MS, easing: "ease-out" });
  }, [landedAt]);

  return (
    <article
      ref={card}
      aria-label={info.title}
      aria-busy={isHearing || isPending}
      data-tone={toneOf(likeliest) ?? "neutral"}
      // A card of its own, which the orb's wisps flow into (energy-wisps.tsx). Its edge takes a little
      // of the tone its model heard.
      data-signal-target
      className="tone-scope tone-scope-instant @container lane-card flex min-w-0 flex-col gap-lane rounded-2xl border p-3 lg:rounded-3xl lg:p-card"
    >
      {/* The reading landing: a ring of the tone's colour that bursts and fades, and a band of light
          that drops through the card from where the wisps come in. Drawn afresh for each reading,
          and over a reading already shown in full, so it holds nothing back. */}
      {reading ? (
        <span
          key={reading.arrivedMs}
          aria-hidden="true"
          className="lane-impact motion-reduce:hidden"
        />
      ) : null}
      <header className="flex items-baseline justify-between gap-2 border-b pb-2 text-xs leading-none font-medium tracking-widest whitespace-nowrap uppercase">
        <h2 className="truncate text-foreground">{info.title}</h2>
        {/* What it reads is dropped where the lane is too narrow for both; that it gave no reading never is. */}
        <span
          className={cn(
            "text-muted-foreground",
            !hasMissed && "hidden @[15rem]:inline",
          )}
        >
          {hasMissed ? NO_READING : info.reads}
        </span>
      </header>
      <LatencyReadout
        // The bot's own measure of the read, or until it arrives, how long the reading took to land.
        ms={reading ? (readMs ?? reading.arrivedMs) : undefined}
        stoppedAt={stoppedAt}
        isPending={isPending}
      />
      <div className="relative">
        <div
          // A reading is shown in full the moment it lands, with a flash that starts bright and
          // settles, so nothing waits on an animation. Keyed by the reading, each one flashes.
          key={reading?.arrivedMs ?? "none"}
          className={cn(
            "flex flex-col gap-lane",
            reading && "animate-landed motion-reduce:animate-none",
            isHearing && "animate-hearing motion-reduce:animate-none",
            isPending && "animate-assessing motion-reduce:animate-none",
          )}
        >
          <LaneHeadline
            title={info.feeling.title}
            word={likeliest}
            badge={<SincerityBadge sincerity={sincerity?.sincerity} />}
            colorClassName="text-tone-now"
          />
          <FeelingPanels title={info.feeling.title} feelings={feelings} />
          {/* The outer gauges sit flush with the panels' edges. A lane with one has it in the middle. */}
          <div className="flex justify-between gap-1 *:only:mx-auto">
            {info.measures.map((measure) => (
              <DotGauge
                key={measure.name}
                measure={measure}
                value={valueOf(signals, measure.name)}
              />
            ))}
          </div>
        </div>
        {/* What the lane is waiting on, over the reading it will fill. The header's status line is what assistive technology is told. */}
        {working ? (
          <p
            aria-hidden="true"
            className={`pointer-events-none absolute inset-0 flex items-center justify-center font-display text-overlay leading-none font-black tracking-widest uppercase motion-reduce:animate-none ${working.pulse}`}
          >
            {working.word}
          </p>
        ) : null}
      </div>
    </article>
  );
}
