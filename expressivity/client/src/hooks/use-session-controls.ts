import {
  useMediaState,
  usePipecatClient,
  usePipecatClientMicControl,
} from "@pipecat-ai/client-react";

import { unlockBotAudio } from "@/components/pipecat/bot-audio";
import { cancelAdvance } from "@/lib/clip-cycle";
import { ensureSession } from "@/lib/pipecat-client";
import { usePerceptionStore } from "@/stores/perception-store";
import type { ClipInfo } from "@/types/perception";

const START_FAILED = "Couldn't connect. Try again.";

/**
 * The clip a run plays next: the first, or the one after `lastClipId` in the
 * bot's list, round to the first again. Undefined before the clips are known.
 */
function clipInOrder(
  clips: ClipInfo[],
  lastClipId: string | null,
): string | undefined {
  const last = clips.findIndex((clip) => clip.id === lastClipId);
  return clips[(last + 1) % clips.length]?.id;
}

interface SessionControls {
  /** Starts running through the clips in order, from the first, or stops. */
  toggleClips: () => void;
  /** Plays the clip after the last one now, in place of any clip playing. */
  nextClip: () => void;
  /** Plays the clip of that id, on its own. */
  playClip: (clipId: string) => void;
  /** Turns the microphone on or off. Turning it on stops the clips. */
  toggleMic: () => void;
  /** Whether clips are playing: one is, or the next of a run is about to. */
  isPlayingClips: boolean;
  isClipPlaying: boolean;
  /** Whether the microphone is on and being heard. */
  isMicOn: boolean;
  /** Whether the browser refused the microphone, or has none. */
  isMicUnavailable: boolean;
}

/**
 * What a visitor can do. Each one starts a session first if there isn't one,
 * and a clip and the microphone are never heard together.
 */
export function useSessionControls(): SessionControls {
  const client = usePipecatClient();
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();
  const isMicUnavailable = useMediaState().mic.state === "error";
  // A microphone that failed to open is asked for but isn't on: pressing again retries it.
  const isMicOn = isMicEnabled && !isMicUnavailable;
  const isClipPlaying = usePerceptionStore(
    (state) => state.activeClipId !== null,
  );
  const isCycling = usePerceptionStore((state) => state.isCycling);
  const setCycling = usePerceptionStore((state) => state.setCycling);
  const setConnectionError = usePerceptionStore(
    (state) => state.setConnectionError,
  );

  /** Runs an action once a session is up. */
  const inSession = (action: () => void) => {
    if (!client) return;
    // Inside the tap, so browsers let the clips be heard later.
    unlockBotAudio();
    setConnectionError(null);
    ensureSession(client).then(action, () => {
      setCycling(false);
      setConnectionError(START_FAILED);
    });
  };

  /** Plays a clip: the one named, or the next of the list, which `fromStart` makes the first. */
  const play = (clipId?: string, fromStart = false) => {
    cancelAdvance();
    inSession(() => {
      enableMic(false);
      // The clips are known once the session is: read now, not when the button was drawn.
      const { clips, lastClipId } = usePerceptionStore.getState();
      const chosen =
        clipId ?? clipInOrder(clips, fromStart ? null : lastClipId);
      // Before the clips are known, the bot plays the first of its own list, which is the same one.
      client?.sendClientMessage(
        "play-clip",
        chosen ? { clipId: chosen } : undefined,
      );
    });
  };

  /** Stops the clips: the one playing, and the run through the rest. */
  const stopClips = () => {
    cancelAdvance();
    setCycling(false);
    client?.sendClientMessage("stop-clip");
  };

  return {
    toggleClips: () => {
      if (isCycling || isClipPlaying) {
        stopClips();
        return;
      }
      setCycling(true);
      play(undefined, true);
    },
    nextClip: () => play(),
    playClip: (clipId) => {
      setCycling(false);
      play(clipId);
    },
    toggleMic: () => {
      if (isMicOn) {
        enableMic(false);
        return;
      }
      inSession(() => {
        stopClips();
        enableMic(true);
      });
    },
    isPlayingClips: isCycling || isClipPlaying,
    isClipPlaying,
    isMicOn,
    isMicUnavailable,
  };
}
