import { useSessionStatus } from "@/hooks/use-session-status";
import { labelsOf, OVERALL, type Tone, toneOf } from "@/lib/perception";
import { usePerceptionStore } from "@/stores/perception-store";

/** What colours the page: the tone of the reading on show, or that a turn is in progress. */
export type SceneTone = Tone | "listening";

/**
 * The colour the page and the pill are in. A turn in progress has its own,
 * so the neutral it starts from and a reading of "neutral" aren't lost in
 * each other. A reading takes over with the feeling the bot concluded from
 * the voice and the words together.
 */
export function useSceneTone(): SceneTone {
  const status = useSessionStatus();
  const tone = usePerceptionStore((state) =>
    toneOf(labelsOf(state.overall ?? undefined, OVERALL.feeling)?.[0]?.label),
  );
  if (tone) return tone;
  return status === "hearing" || status === "reading" ? "listening" : "neutral";
}
