import {
  MicIcon,
  MicOffIcon,
  PlayIcon,
  SkipForwardIcon,
  SquareIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSessionControls } from "@/hooks/use-session-controls";
import { useSessionStatus } from "@/hooks/use-session-status";
import { usePerceptionStore } from "@/stores/perception-store";

const PLAY = "Play the clips in order";
const STOP = "Stop the clips";
const NEXT = "Play the next clip";
const MIC_ON = "Turn on the microphone";
const MIC_OFF = "Turn off the microphone";
const MIC_UNAVAILABLE = "The microphone is unavailable. Check its permission.";

const BUTTON_CLASSES =
  "size-control rounded-full [&_svg:not([class*='size-'])]:size-6";

/** The demo's controls: run through the clips, skip to the next, or open the microphone. */
export function SessionControls() {
  const {
    toggleClips,
    nextClip,
    toggleMic,
    isPlayingClips,
    isMicOn,
    isMicUnavailable,
  } = useSessionControls();
  const isConnecting = useSessionStatus() === "connecting";
  const connectionError = usePerceptionStore((state) => state.connectionError);
  const error = connectionError ?? (isMicUnavailable ? MIC_UNAVAILABLE : null);

  return (
    <div className="flex flex-col items-center gap-frame-sm">
      <div className="flex items-center gap-4">
        <Button
          size="icon-lg"
          disabled={isConnecting}
          aria-label={isPlayingClips ? STOP : PLAY}
          onClick={toggleClips}
          className={BUTTON_CLASSES}
        >
          {isPlayingClips ? (
            <SquareIcon className="fill-current" />
          ) : (
            <PlayIcon className="fill-current" />
          )}
        </Button>
        <Button
          variant="outline"
          size="icon-lg"
          disabled={isConnecting}
          aria-label={NEXT}
          onClick={nextClip}
          className={BUTTON_CLASSES}
        >
          <SkipForwardIcon className="fill-current" />
        </Button>
        {/* Clips on one side, the microphone on the other. */}
        <span
          aria-hidden="true"
          className="size-1 rounded-full bg-muted-foreground/60"
        />
        <Button
          variant={isMicOn ? "default" : "outline"}
          size="icon-lg"
          disabled={isConnecting}
          aria-pressed={isMicOn}
          aria-label={isMicOn ? MIC_OFF : MIC_ON}
          onClick={toggleMic}
          className={BUTTON_CLASSES}
        >
          {isMicOn ? <MicIcon /> : <MicOffIcon />}
        </Button>
      </div>
      {/* Always a line tall, so an error doesn't push the pill up. */}
      <p role="alert" className="min-h-5 text-center text-sm text-destructive">
        {error}
      </p>
    </div>
  );
}
