import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export interface PanelProps {
  /** Legend printed over the top border, at the left. */
  title: string
  /** Status printed over the top border, at the right. */
  status?: ReactNode
  /** Note printed over the bottom border, at the left. */
  footnote?: ReactNode
  className?: string
  children?: ReactNode
}

// Legends sit *on* the rule and paint the page background over it, so the
// border reads as broken around them — a fieldset legend, without the
// fieldset's layout. z-10 keeps them above panel contents, which are
// declared after them.
const LEGEND =
  "absolute z-10 bg-background px-1.5 text-[13px] leading-none font-medium"

/**
 * A bordered region of the UI, labelled on its own border. Panels carry no
 * padding: their contents own it, so a divider inside one can run the full
 * height of the interior.
 */
export function Panel({
  title,
  status,
  footnote,
  className,
  children,
}: PanelProps) {
  return (
    <section className={cn("relative border border-border", className)}>
      <span className={cn(LEGEND, "top-0 left-3 -translate-y-1/2 text-agent")}>
        {title}
      </span>
      {status !== undefined && (
        <span className={cn(LEGEND, "top-0 right-3 -translate-y-1/2")}>
          {status}
        </span>
      )}
      {footnote !== undefined && (
        <span
          className={cn(
            LEGEND,
            "bottom-0 left-3 translate-y-1/2 text-muted-foreground/70"
          )}
        >
          {footnote}
        </span>
      )}
      {children}
    </section>
  )
}
