/** Behind everything: a faint grid of dots, and two soft glows in the colours of the tone on show. */
export function Backdrop() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-10 overflow-clip"
    >
      <div className="absolute backdrop-glow" />
      <div className="absolute backdrop-glow-2" />
      <div className="absolute inset-0 backdrop-dots" />
    </div>
  );
}
