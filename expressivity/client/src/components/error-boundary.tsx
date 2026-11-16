import { Component, type ErrorInfo, type ReactNode } from "react";

const TITLE = "Something went wrong";
const HINT = "Reload the page to start again.";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  failed: boolean;
}

/** Keeps a component failure from blanking the whole page. */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-2 p-6 text-center">
        <h1 className="font-display text-3xl font-black uppercase">{TITLE}</h1>
        <p role="alert" className="text-muted-foreground">
          {HINT}
        </p>
      </main>
    );
  }
}
