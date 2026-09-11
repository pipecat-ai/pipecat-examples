import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores([
    'dist',
    // Source installed from the shadcn registries (ui.shadcn.com and
    // ui.pipecat.ai). Lint your own code, not theirs.
    'src/components/ui/**',
    'src/components/pipecat/**',
    'src/hooks/use-pipecat-app.ts',
    'src/lib/transports.ts',
    'src/lib/visualizer.ts',
  ]),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
])
