import { usePipecatClientMediaTrack } from "@pipecat-ai/client-react";

import { useSessionControls } from "@/hooks/use-session-controls";

/** The audio the model is hearing right now: the clip being played, the microphone, or nothing. */
export function useHeardVoice(): MediaStreamTrack | null {
  const { isClipPlaying, isMicOn } = useSessionControls();
  const clipTrack = usePipecatClientMediaTrack("audio", "bot");
  const micTrack = usePipecatClientMediaTrack("audio", "local");
  return isClipPlaying ? clipTrack : isMicOn ? micTrack : null;
}
