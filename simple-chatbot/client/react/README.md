# React Implementation

Basic implementation using the [Pipecat React SDK](https://docs.pipecat.ai/client/react/introduction) and UI components from the [Pipecat UI](https://ui.pipecat.ai) shadcn registry.

The connect button, microphone control, conversation transcript, text input, and the `usePipecatApp` / `usePipecatEventStream` hooks are copied into this project from the registry (see `src/components/pipecat/` and `src/hooks/`), so they can be edited like any other source file.

## Setup

1. Run the server-side bot; see [README](../../server/README.md).

2. Navigate to the `client/react` directory:

```bash
cd client/react
```

3. Install dependencies:

```bash
npm install
```

4. Configure the bot start URL (defaults to a local server on port 7860):

```bash
cp env.example .env.local
```

5. Run the client app:

```bash
npm run dev
```

6. Visit http://localhost:3000 in your browser.

## Pipecat UI components

The components were added with the shadcn CLI. The `@pipecat` registry is already registered in `components.json`; in a new project, register it first, then add components:

```bash
npx shadcn@latest registry add @pipecat
npx shadcn@latest add @pipecat/connect-button @pipecat/user-audio-control @pipecat/conversation @pipecat/text-input @pipecat/use-pipecat-app @pipecat/use-pipecat-event-stream
```

Installed components are not updated automatically. To pull in upstream changes, review the diff first, then re-add the component and merge any local edits:

```bash
npx shadcn@latest add @pipecat/user-audio-control --diff
npx shadcn@latest add @pipecat/user-audio-control
```

See [Editing and updating](https://ui.pipecat.ai/docs/updating) for details.
