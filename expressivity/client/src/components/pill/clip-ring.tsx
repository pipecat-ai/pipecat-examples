import { useShallow } from "zustand/react/shallow";

import { cn } from "@/lib/utils";
import { usePerceptionStore } from "@/stores/perception-store";

/** How many dots the ring has, and how far out they sit, as a share of the pill's place. */
const DOTS = 96;
const RADIUS = 50;

/** Where each dot sits, clockwise from the top. */
const POSITIONS = Array.from({ length: DOTS }, (_, index) => {
  const angle = ((-90 + (index * 360) / DOTS) * Math.PI) / 180;
  return {
    left: `${(50 + RADIUS * Math.cos(angle)).toFixed(3)}%`,
    top: `${(50 + RADIUS * Math.sin(angle)).toFixed(3)}%`,
  };
});

/**
 * A ring of dots round the pill that fills as a clip plays: each dot lights
 * when the clip reaches its share of the way through. Dark when no clip is
 * playing.
 */
export function ClipRing() {
  const { clipCount, duration } = usePerceptionStore(
    useShallow((state) => ({
      clipCount: state.clipCount,
      duration:
        state.clips.find((clip) => clip.id === state.activeClipId)?.duration ??
        null,
    })),
  );

  return (
    <div
      // A new clip starts the ring afresh.
      key={clipCount}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0"
    >
      {POSITIONS.map((position, index) => (
        <span
          // The dots never reorder, so their position identifies them.
          key={index}
          className={cn(
            "absolute size-1 -translate-1/2 rounded-full bg-meter-track",
            duration !== null && "animate-ring-dot motion-reduce:animate-none",
          )}
          // Each dot's place on the ring, and its moment in the clip.
          style={{
            ...position,
            animationDelay:
              duration === null ? undefined : `${(index / DOTS) * duration}s`,
          }}
        />
      ))}
    </div>
  );
}
