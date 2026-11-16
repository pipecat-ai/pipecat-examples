<!-- pc-client-init: 2026-11-07 -->
# Client — Agent Guidelines

These are the mandatory standards for all frontend code in `client/`. Follow them for every change, whether you are scaffolding, adding a feature, or fixing a bug. If a request conflicts with these rules, call out the conflict before proceeding.

## Stack

| Concern         | Choice                                                                  |
| --------------- | ----------------------------------------------------------------------- |
| Build           | Vite (latest) + `@vitejs/plugin-react`                                  |
| UI              | React 19, TypeScript (strict)                                           |
| Components      | shadcn/ui (`base-nova` style, Base UI primitives) + Pipecat UI registry |
| Styling         | Tailwind CSS 4 via `@tailwindcss/vite`                                  |
| Voice / realtime | `@pipecat-ai/client-js`, `@pipecat-ai/client-react`, a Pipecat transport |
| State           | Zustand                                                                 |
| Lint / format   | ESLint (flat config) + Prettier (`prettier-plugin-tailwindcss`)         |
| Runtime         | Node.js 22+                                                             |

Always install the latest stable releases. Use the package manager the lockfile indicates, and never mix managers or commit a second lockfile. Ask before adding a dependency that isn't listed here, and prefer what's already installed.

## Project structure

```
client/
├── components.json          # shadcn config (includes the @pipecat registry)
├── index.html
├── vite.config.ts
├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
├── eslint.config.js
└── src/
    ├── main.tsx             # entry: providers only
    ├── app.tsx              # top-level layout
    ├── index.css            # Tailwind import + design tokens (single source of truth)
    ├── components/
    │   ├── ui/              # shadcn primitives (generated)
    │   ├── pipecat/         # Pipecat UI registry components (generated)
    │   └── <feature>/       # app components, grouped by feature
    ├── stores/              # Zustand stores, one file per domain
    ├── hooks/               # reusable custom hooks
    ├── lib/                 # utils.ts (cn), pipecat client factory, pure helpers
    └── types/               # shared types
```

- Use the `@/` alias for `src/` and never write deep relative imports (`../../../`).
- Use kebab-case for file names (`session-panel.tsx`) and PascalCase for component names (`SessionPanel`).
- Use named exports. The only default exports allowed are files that a tool requires to use them, such as config files.
- Don't create barrel `index.ts` files.

## Components: shadcn + Pipecat UI

- **Reach for existing components first.** Before writing UI, check `components/ui` and `components/pipecat`, then the shadcn and [Pipecat UI](https://ui.pipecat.ai/) registries. Hand-rolling a button, dialog, select, or similar element is not allowed.
- **Add components with the CLI. Never copy them in by hand:**
  ```bash
  npx shadcn@latest add button dialog
  npx shadcn@latest registry add @pipecat          # once per project
  npx shadcn@latest add @pipecat/connect-button @pipecat/conversation
  ```
- **Keep the `base-nova` style.** Pipecat UI is built and tested against it, and switching styles later doesn't regenerate primitives that are already installed.
- **Treat generated primitives as vendored code.** Customize `components/ui/*` and `components/pipecat/*` through composition, props, and `className` first. Edit their source only when composition can't do the job. Keep those edits minimal and add a short comment saying why.
- **Choose between connected and `*View` components:**
  - Use **connected components** (`ConnectButton`) when the component sits under `PipecatClientProvider`. This is the default.
  - Use **`*View` components** (`ConnectButtonView`) when you need full control through props, or when rendering outside the provider, such as in previews or Storybook-style tests.
- **Build variants with `cva`, and merge classes with `cn()`** from `@/lib/utils`.
- **Keep components small and focused.** If a file is growing past roughly 200 lines or does more than one job, split it.

## Styling: Tailwind 4 and design tokens

- **Configure Tailwind in CSS.** It is CSS-first: tokens live in `src/index.css` under `@theme` / `@theme inline` as CSS variables, and there is no `tailwind.config.js`.
- **Every color, radius, shadow, and font goes through a token.** Use semantic utilities (`bg-background`, `text-muted-foreground`, `border-border`, `bg-primary`), plus the Pipecat token groups (`active`/`inactive`, `agent`/`client`).
- **Don't hard-code values.** That means no hex or RGB colors in components, no arbitrary values (`text-[13px]`, `bg-[#111]`, `w-[347px]`) unless the reason is documented, and no inline `style` except for truly dynamic values such as a computed visualizer height.
- **Add a token when one is missing.** Define it in `index.css` for both light and dark, then use it. Don't sneak in a one-off value.
- **Support dark mode** through the `.dark` class and token overrides. Never use per-component `dark:` color hacks for values a token should carry.
- **Keep class lists readable.** Let Prettier sort them. Pull repeated combinations into a component or `cva` variant, and don't use `@apply` in feature code.

## Pipecat client

- **Use the current Pipecat libraries:** `@pipecat-ai/client-js`, `@pipecat-ai/client-react`, and one transport, such as `@pipecat-ai/small-webrtc-transport` or `@pipecat-ai/daily-transport`. Don't use the deprecated `@pipecat-ai/voice-ui-kit` package.
- **Use one client per app.** Create the `PipecatClient` once, in a factory in `src/lib/` or a stable `useState` initializer, and provide it through `PipecatClientProvider` in `main.tsx` or `app.tsx`. Render `PipecatClientAudio` inside the provider.
- **Read client state through the SDK hooks** instead of re-implementing it: `usePipecatClient`, `usePipecatClientTransportState`, `usePipecatConversation`, `useMediaSupport`, and `useRTVIClientEvent` for events.
- **Don't copy SDK state into Zustand.** Transport state, devices, and conversation already have hooks. Bridge an RTVI event into a store only for app-specific state derived from it.
- **Keep secrets out of the browser.** API keys belong to the server only. The client starts sessions through the server's endpoint. Only `VITE_`-prefixed variables reach the client, and those must hold non-secret values such as URLs or feature flags. Document each one in `client/env.example`.

## State: Zustand first

- **Put shared and UI state in Zustand stores.** Each store lives in `src/stores/<domain>-store.ts`, with typed state and actions defined together.
- **Subscribe with selectors.** Write `useSessionStore((s) => s.status)`, use `useShallow` when picking several fields, and never destructure the whole store.
- **Put logic in store actions** rather than components. Components read state and call actions.
- **Use `useState` only for state local to one component,** such as an input value or whether a popover is open.
- **Don't create React Context for app state.** Context is reserved for providers that libraries require.

## React practices

- **Use effects only to sync with an external system.** Valid cases include subscribing to an API outside React, or a DOM integration with no declarative option. Anything else is an anti-pattern, specifically:
  - deriving state (compute it during render instead),
  - reacting to events (handle them in the event handler or a store action),
  - chaining state updates,
  - fetching data inside an effect without cleanup or cancellation.
- **Use `useRef` only for DOM nodes and imperative handles,** such as canvas or media elements. Don't use refs as mutable app state or to dodge re-renders; that state belongs in Zustand.
- **Skip `useMemo`, `useCallback`, and `memo` by default.** Use them only when a library requires them or profiling shows a problem. Enable the React Compiler if the project supports it.
- **Write pure components.** Rendering must have no side effects, and data flows in through props or store selectors.
- **Give lists stable keys,** never array indexes, for items that can reorder.
- **Wrap the app in an error boundary** so a component failure doesn't blank the whole UI. Show connection and permission errors (mic or camera denied) to the user and never fail silently.

## TypeScript, linting, and tooling

- **Make `tsconfig` strict:** `strict`, `noUncheckedIndexedAccess`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, `verbatimModuleSyntax`, `moduleResolution: "bundler"`, and the `@/*` path alias. Keep it in sync with `vite.config.ts`.
- **Keep types honest.**
  - Don't use `any`. Use `unknown` and narrow it.
  - Don't use non-null `!` assertions without a comment saying why.
  - Don't use `@ts-ignore`. If a suppression is unavoidable, use `@ts-expect-error` with a reason.
  - Use `import type` for type-only imports.
- **Configure ESLint as a flat config** with `typescript-eslint` (type-checked rules), `eslint-plugin-react-hooks` (recommended, including compiler rules), and `eslint-plugin-react-refresh`. Lint warnings are errors.
- **Format with Prettier and `prettier-plugin-tailwindcss`,** and don't hand-format code.
- **Provide these scripts in `package.json`:** `dev`, `build` (`tsc -b && vite build`), `preview`, `lint`, `typecheck`, and `format`.

## Responsive layout

- **Design mobile-first:** base styles target small screens, and `sm:` `md:` `lg:` `xl:` `2xl:` layer up from there.
- **Every view must work at these widths:** about 375px (phone), 768px (tablet), 1280px (laptop), and 1920px or wider (wide screen). On wide screens, cap content width (`max-w-*`) instead of stretching it.
- **Use container queries (`@container`)** for components that live in panels of varying width.
- **Use flex and grid with `gap`.** Avoid fixed widths and heights, add `min-w-0` to flex children that hold text, and make no assumptions about viewport height.
- **Handle mobile browser chrome** with `h-dvh` / `min-h-dvh` instead of `h-screen`, and respect safe-area insets on mobile.
- **Make touch targets at least 44×44px.** Hover-only affordances must have a touch or focus equivalent.

## Accessibility

- **Use semantic HTML** (`button`, `nav`, `main`, `section`, headings in order). Never put a click handler on a `div`.
- **Give every control an accessible name.** Icon-only buttons need `aria-label`, and form fields need labels.
- **Keep focus visible** and keep everything usable from the keyboard.
- **Announce changes in live regions.** That includes connection status and new transcript lines.
- **Respect `prefers-reduced-motion`,** especially for audio visualizers and animations.
- **Rely on tokens for contrast.** Don't put text on a color without a matching `*-foreground` token.

## Code hygiene

- Leave no `console.log`, no commented-out code, and no unused exports, files, or dependencies.
- Match the surrounding code's style and patterns, and don't refactor unrelated code in the same change.
- Comments explain *why*, not *what*. Keep them rare and useful.
- Put copy and constants in clear named constants, never magic strings or numbers buried in JSX.
- Delete scaffold leftovers such as the Vite logos and the demo counter.

## Definition of done

Before calling client work finished:

1. `typecheck`, `lint`, and `build` all pass with zero warnings.
2. The UI has been checked at phone, tablet, desktop, and wide widths, in both light and dark mode.
3. There are no hard-coded colors or spacing, no new `useEffect` or `useRef` without a valid reason, and no secrets in client code.
4. Any new env vars are added to `client/env.example`.
