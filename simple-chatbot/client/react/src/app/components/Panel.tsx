import { cn } from "@/lib/utils";

/** Bordered card with an optional header; mirrors the voice-ui-kit Panel layout. */
export function Panel({ className, ...props }: React.ComponentProps<"section">) {
  return (
    <section
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-lg border bg-card text-card-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function PanelHeader({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center gap-4 border-b p-3",
        className,
      )}
      {...props}
    />
  );
}

/** Uppercase monospace title, matching the voice-ui-kit panel titles. */
export function PanelTitle({
  className,
  ...props
}: React.ComponentProps<"h2">) {
  return (
    <h2
      className={cn(
        "font-mono text-xs leading-none font-bold tracking-wider uppercase",
        className,
      )}
      {...props}
    />
  );
}

export function PanelContent({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("flex min-h-0 flex-1 flex-col gap-3 p-3", className)}
      {...props}
    />
  );
}
