import { useShallow } from "zustand/react/shallow";

import { usePerceptionStore } from "@/stores/perception-store";

const MICROPHONE = "Microphone";
const CLIP = "Clip";

/** What the turn on show is, a clip by how it was said and who says it or the microphone, and the words heard in it. */
export function TurnCaption() {
  const { clips, turnClipId, words } = usePerceptionStore(
    useShallow((state) => ({
      clips: state.clips,
      turnClipId: state.turnClipId,
      words: state.words,
    })),
  );
  const clip = clips.find((candidate) => candidate.id === turnClipId);
  const source =
    turnClipId === undefined
      ? null
      : clip
        ? `${CLIP} · ${clip.mood} · ${clip.sincerity} · ${clip.voice}`
        : MICROPHONE;

  return (
    <p className="flex min-h-4 justify-between gap-6 text-xs font-medium tracking-widest text-muted-foreground uppercase">
      <span className="truncate sm:shrink-0">{source}</span>
      {words ? (
        <span className="hidden truncate sm:block">&ldquo;{words}&rdquo;</span>
      ) : null}
    </p>
  );
}
