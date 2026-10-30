# Frontend

React, Vite, TypeScript (strict), Tailwind CSS and shadcn/ui. Stack and rules are fixed in `AGENTS.md` and `docs/design-system.md`. The installed versions and the reasons for them are in ADR-025 in `docs/decisions.md`.

## Working on it

Needs Node 22 (`.nvmrc`). With nvm, `nvm use` in this folder picks it, and the `make` targets refuse to run on another version.

From the repository root:

| Command                 | Purpose                                       |
| ----------------------- | --------------------------------------------- |
| `make frontend-install` | Install exactly what `package-lock.json` says |
| `make frontend-dev`     | Dev server on http://localhost:5173           |
| `make frontend-check`   | ESLint, Prettier check, TypeScript and Vitest |

Or from this folder: `npm run dev`, `npm run build`, `npm test`, `npm run lint`, `npm run format`.

The dev server proxies `/api` to the backend on port 8000, so cookies stay same-origin, matching production (ADR-008). If port 8000 is busy, set `API_PROXY_TARGET` (for example `API_PROXY_TARGET=http://localhost:8001 make frontend-dev`). The backend must have `JWT_SECRET` set and `http://localhost:5173` in `CORS_ORIGINS`, which is the default.

## Structure

```
src/
  app/          App, providers, routes, guards, layouts
  pages/        route components, thin
  features/     auth/  (api calls, store, refresh, hooks, forms, schemas)
  components/ui/ shadcn components, changed only to follow the design tokens
  lib/          api.ts (the only place that calls fetch), query-client.ts, utils.ts
  styles/       tokens.css (design tokens), index.css (Tailwind and the theme mapping)
  test/         shared test helpers
```

## Rules that are enforced by ESLint

- `fetch` is only called in `src/lib/api.ts`.
- `localStorage` and `sessionStorage` are never used, because the access token stays in memory (`docs/security.md`).
- No `dangerouslySetInnerHTML`, no non-null assertions, no `any`.

## Adding a shadcn/ui component

`npx shadcn@latest add <name>` (Node 22). Then check the generated file against `docs/design-system.md`: no shadows, the 2 px focus ring with a 2 px offset, and only the semantic color names. The theme maps shadcn's color names to our tokens in `src/styles/index.css`.
