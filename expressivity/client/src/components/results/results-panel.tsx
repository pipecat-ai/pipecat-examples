import { ModelLane } from "@/components/results/model-lane";
import { Conclusion } from "@/components/results/conclusion";
import { MODELS } from "@/types/perception";

const LABEL = "Readings";

/** What the two models made of the turn on show, and under them, what the two readings add up to. */
export function ResultsPanel() {
  return (
    <section
      aria-label={LABEL} // On a larger screen there is room above the cards for the orb's wisps to come over them.
      className="flex min-w-0 flex-col gap-lane lg:pt-rail"
    >
      <div className="grid grid-cols-2 gap-x-3 lg:gap-x-8">
        {MODELS.map((model) => (
          <ModelLane key={model} model={model} />
        ))}
      </div>
      <Conclusion />
    </section>
  );
}
