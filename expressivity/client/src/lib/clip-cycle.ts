/** How long a clip's reading stays on show before the next clip of a pass starts. */
const PAUSE_MS = 3000;

let pending: ReturnType<typeof setTimeout> | undefined;

/** Move on to the next clip once this one's reading has had its moment. */
export function advanceAfterPause(advance: () => void): void {
  cancelAdvance();
  pending = setTimeout(advance, PAUSE_MS);
}

/** Call off the move to the next clip, if one is waiting. */
export function cancelAdvance(): void {
  clearTimeout(pending);
  pending = undefined;
}
