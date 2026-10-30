import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import prettier from 'eslint-config-prettier'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default defineConfig([
  globalIgnores(['dist', 'coverage']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: { globals: globals.browser },
    rules: {
      // AGENTS.md: no non-null assertions to silence the compiler.
      '@typescript-eslint/no-non-null-assertion': 'error',
      // AGENTS.md: components never call fetch, and the access token never goes to browser
      // storage (docs/security.md). src/lib/api.ts is the one place allowed to call fetch.
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Use apiRequest from src/lib/api.ts.' },
        { name: 'localStorage', message: 'Tokens must stay in memory (docs/security.md).' },
        { name: 'sessionStorage', message: 'Tokens must stay in memory (docs/security.md).' },
      ],
      // AGENTS.md: never render model or server text as HTML.
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'Never render text as HTML.',
        },
      ],
    },
  },
  {
    // The API client is the one place that calls fetch. Tests stub fetch and check storage.
    files: ['src/lib/api.ts', 'src/**/*.test.{ts,tsx}', 'src/test/**'],
    rules: { 'no-restricted-globals': 'off' },
  },
  {
    files: ['vite.config.ts', 'eslint.config.js'],
    languageOptions: { globals: globals.node },
  },
  // Last, so that formatting is left to Prettier and never argued about in lint.
  prettier,
])
