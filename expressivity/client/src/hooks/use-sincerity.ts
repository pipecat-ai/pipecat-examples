import {
  MODEL_INFO,
  type SincerityReading,
  sincerityOf,
} from "@/lib/perception";
import { usePerceptionStore } from "@/stores/perception-store";
import type { Model } from "@/types/perception";

/** Whether the turn on show was meant, as one model read it, or undefined before its reading. */
export function useSincerity(model: Model): SincerityReading | undefined {
  const signals = usePerceptionStore((state) => state.readings[model]?.signals);
  return sincerityOf(signals, MODEL_INFO[model].sarcasm);
}
