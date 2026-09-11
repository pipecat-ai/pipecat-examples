import { useEffect } from "react";

/**
 * Reports the volume of a MediaStreamTrack as a number between 0 and 1,
 * roughly once per animation frame.
 */
export function useAudioLevel(
  track: MediaStreamTrack | null,
  onLevel: (level: number) => void
) {
  useEffect(() => {
    if (!track) return;

    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(
      new MediaStream([track])
    );
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.6;
    source.connect(analyser);

    const samples = new Uint8Array(analyser.fftSize);
    let frame = 0;

    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) {
        const v = (sample - 128) / 128;
        sum += v * v;
      }
      // RMS of speech is small, so scale it up to a usable 0-1 range
      onLevel(Math.min(1, Math.sqrt(sum / samples.length) * 4));
      frame = requestAnimationFrame(tick);
    };
    tick();

    return () => {
      cancelAnimationFrame(frame);
      source.disconnect();
      audioContext.close();
    };
  }, [track, onLevel]);
}
