"use client"

import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export interface MetricProps {
  /** What the reading is, in the muted label colour. */
  label: ReactNode
  /** The formatted reading; null prints the empty dash instead. */
  value?: ReactNode | null
  /**
   * "inline" sets the label and value on one row, label left and value
   * right — a dense readout. "stack" prints the value large under a small
   * label — a counter you can read across the room.
   */
  layout?: "inline" | "stack"
  /** Colour (or transition) for the value; ignored when there is none. */
  valueClassName?: string
  className?: string
}

/**
 * One reading, in either of the two shapes this UI uses. Fully generic and
 * props-driven — it renders whatever value it is handed and never reads
 * Pipecat state itself, so it works for any realtime number. Pair it with
 * a data source (usePipecatMetricValue, useToolCallFlash) to make it live.
 */
export function Metric({
  label,
  value,
  layout = "inline",
  valueClassName,
  className,
}: MetricProps) {
  const isEmpty = value === null || value === undefined

  if (layout === "stack") {
    return (
      <div data-slot="metric" data-state={isEmpty ? "empty" : "live"} className={className}>
        <div
          data-slot="metric-label"
          className="truncate text-[11px] leading-4 text-muted-foreground"
        >
          {label}
        </div>
        <div
          data-slot="metric-value"
          className={cn(
            "mt-1 text-[30px] leading-none font-medium tabular-nums",
            isEmpty ? "text-muted-foreground/50" : valueClassName,
          )}
        >
          {isEmpty ? "–" : value}
        </div>
      </div>
    )
  }

  return (
    <div
      data-slot="metric"
      data-state={isEmpty ? "empty" : "live"}
      className={cn("flex items-baseline justify-between gap-3", className)}
    >
      <span data-slot="metric-label" className="truncate text-muted-foreground">
        {label}
      </span>
      <span
        data-slot="metric-value"
        className={cn(
          "tabular-nums",
          isEmpty ? "text-muted-foreground/50" : (valueClassName ?? "text-foreground"),
        )}
      >
        {isEmpty ? "–" : value}
      </span>
    </div>
  )
}
