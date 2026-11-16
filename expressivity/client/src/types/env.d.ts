interface ImportMetaEnv {
  /** Which Pipecat transport the client connects with: "daily" (default) or "smallwebrtc". */
  readonly VITE_TRANSPORT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
