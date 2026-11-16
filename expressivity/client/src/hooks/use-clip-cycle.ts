import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";

import { useSessionControls } from "@/hooks/use-session-controls";
import { advanceAfterPause, cancelAdvance } from "@/lib/clip-cycle";
import { usePerceptionStore } from "@/stores/perception-store";
import { isServerMessage } from "@/types/perception";

/**
 * Keeps a run through the clips going: when one plays to its end, the next
 * starts after a pause for its reading. Mount once, under the client provider.
 */
export function useClipCycle(): void {
  const { nextClip } = useSessionControls();

  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    // A clip that was stopped doesn't lead on to another.
    if (!isServerMessage(data) || data.type !== "clip-finished") return;
    if (!data.completed || !usePerceptionStore.getState().isCycling) return;
    advanceAfterPause(() => {
      if (usePerceptionStore.getState().isCycling) nextClip();
    });
  });
  useRTVIClientEvent(RTVIEvent.Disconnected, cancelAdvance);
}
