import { figureFor, type Measure, unitOf } from "@/lib/perception";
import { cn } from "@/lib/utils";

const EMPTY = "--";
/** The gauge's dots: how many, the arc they span, and how far out they sit, as a share of its box. */
const DOTS = 28;
const START_DEGREES = 135;
const SWEEP_DEGREES = 270;
const RADIUS = 44.6;

/** Where each dot sits, from the bottom left round to the bottom right. */
const POSITIONS = Array.from({ length: DOTS }, (_, index) => {
  const angle =
    ((START_DEGREES + (index * SWEEP_DEGREES) / (DOTS - 1)) * Math.PI) / 180;
  return {
    left: `${(50 + RADIUS * Math.cos(angle)).toFixed(2)}%`,
    top: `${(50 + RADIUS * Math.sin(angle)).toFixed(2)}%`,
  };
});

interface DotGaugeProps {
  measure: Measure;
  /** The signal's value in the reading on show, or undefined when there is none. */
  value: number | undefined;
}

/** One measured signal as an arc of dots lit up to its value, with the figure in the middle. */
export function DotGauge({ measure, value }: DotGaugeProps) {
  const figure = value === undefined ? null : figureFor(measure, value);
  const lit = figure ? Math.max(1, Math.round(figure.fraction * DOTS)) : 0;
  return (
    <div className="flex min-w-0 flex-col items-center gap-1">
      <div
        role="meter"
        aria-label={measure.title}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round((figure?.fraction ?? 0) * 100)}
        aria-valuetext={figure ? `${figure.text} ${figure.unit}` : undefined}
        className="relative size-gauge"
      >
        {POSITIONS.map((position, index) => (
          <span
            // The dots never reorder, so their position identifies them.
            key={index}
            aria-hidden="true"
            className={cn(
              "absolute size-1 -translate-1/2 rounded-full",
              index >= lit && "bg-meter-track",
              index < lit - 1 && "bg-tone-now",
              index === lit - 1 && "bg-foreground",
            )}
            // Each dot's place on the arc.
            style={position}
          />
        ))}
        <span className="absolute inset-0 flex flex-col items-center justify-center gap-1">
          <span
            className={cn(
              "font-display text-gauge leading-none font-black",
              !figure && "opacity-30",
            )}
          >
            {figure?.text ?? EMPTY}
          </span>
          <span className="text-gauge-unit leading-none text-muted-foreground">
            {unitOf(measure)}
          </span>
        </span>
      </div>
      <span className="text-gauge-unit font-medium tracking-normal whitespace-nowrap text-muted-foreground uppercase lg:tracking-widest">
        {measure.title}
      </span>
    </div>
  );
}
