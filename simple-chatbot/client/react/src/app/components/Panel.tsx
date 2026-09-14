import { cn } from "@/lib/utils";

/** Bordered card with an optional header; mirrors the voice-ui-kit Panel layout. */
export function Panel({ className, ...props }: React.ComponentProps<"section">) {
  return (
    <section
      data-slot="panel"
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
      data-slot="panel-header"
      className={cn(
        "flex shrink-0 items-center justify-center gap-4 border-b p-3",
        className,
      )}
      {...props}
    />
  );
}

export function PanelTitle({
  className,
  ...props
}: React.ComponentProps<"h2">) {
  return (
    <h2
      data-slot="panel-title"
      className={cn("mono-upper", className)}
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
      data-slot="panel-content"
      className={cn("flex min-h-0 flex-1 flex-col gap-3 p-3", className)}
      {...props}
    />
  );
}
