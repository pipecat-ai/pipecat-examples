import { lazy, Suspense } from "react";

import { ClipRing } from "@/components/pill/clip-ring";
import { SimpleOrb } from "@/components/pill/simple-orb";
import { cn } from "@/lib/utils";
import { useEffectsStore } from "@/stores/effects-store";

// The glass pill and its shaders are fetched only when the effects are on.
const GlassPill = lazy(() => import("@/components/pill/glass-pill"));

interface VoicePillProps {
  className?: string;
}

/**
 * What stands for the voice being heard, with the clip ring round it: the
 * glass pill, or with the effects off, a plain circle.
 */
export function VoicePill({ className }: VoicePillProps) {
  const hasEffects = useEffectsStore((state) => state.hasEffects);
  return (
    // The wisps come out of this box (energy-wisps.tsx).
    <div data-signal-source className={cn("relative shrink-0", className)}>
      <div aria-hidden="true" className="absolute pill-bed" />
      <ClipRing />
      {hasEffects ? (
        <Suspense fallback={null}>
          <GlassPill />
        </Suspense>
      ) : (
        <SimpleOrb />
      )}
    </div>
  );
}
