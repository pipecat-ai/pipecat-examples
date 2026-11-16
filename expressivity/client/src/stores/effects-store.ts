import { create } from "zustand";

const STORAGE_KEY = "expressivity:effects";
const QUERY_PARAM = "effects";

/** Whether this browser can draw the glass pill at all. */
function canDrawEffects(): boolean {
  try {
    return document.createElement("canvas").getContext("webgl2") !== null;
  } catch {
    return false;
  }
}

/**
 * What the page's address asks for, `?effects=off` or `?effects=on`, then the
 * visitor's last choice, or with neither, on wherever the browser can draw them.
 */
function initialEffects(): boolean {
  const asked = new URLSearchParams(window.location.search).get(QUERY_PARAM);
  if (asked === "off" || asked === "on") return asked === "on";
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) return stored === "on";
  } catch {
    // Storage can be blocked: the choice then lasts for the visit.
  }
  return canDrawEffects();
}

interface EffectsState {
  /**
   * Whether the page draws its GPU effects: the glass pill, the wisps and the
   * cards' glass. Off, it is a plain circle and plain cards, for a device
   * that struggles with them.
   */
  hasEffects: boolean;
  toggleEffects: () => void;
}

export const useEffectsStore = create<EffectsState>()((set) => ({
  hasEffects: initialEffects(),
  toggleEffects: () =>
    set((state) => {
      const hasEffects = !state.hasEffects;
      try {
        localStorage.setItem(STORAGE_KEY, hasEffects ? "on" : "off");
      } catch {
        // See initialEffects.
      }
      return { hasEffects };
    }),
}));
