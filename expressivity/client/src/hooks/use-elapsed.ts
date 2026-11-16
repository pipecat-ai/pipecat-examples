import { useEffect, useState } from "react";

/**
 * The milliseconds since a moment on the page's clock (performance.now()),
 * counted up every frame while running. Null when there is no moment to
 * count from.
 */
export function useElapsed(
  since: number | null,
  isRunning: boolean,
): number | null {
  const [elapsed, setElapsed] = useState<number | null>(null);

  useEffect(() => {
    if (since === null || !isRunning) return;
    let frame = requestAnimationFrame(function tick() {
      setElapsed(performance.now() - since);
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [since, isRunning]);

  return since === null || !isRunning ? null : elapsed;
}
