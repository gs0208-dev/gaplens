# Frontend

Scaffolded in Sprint 1. Stack and rules are fixed in `AGENTS.md` and `docs/design-system.md`.

## Scaffold (Sprint 1, run once)

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install react-router-dom @tanstack/react-query zustand react-hook-form zod @hookform/resolvers lucide-react
npm install -D tailwindcss @tailwindcss/vite vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom prettier
```

Then initialize shadcn/ui for Vite following the current official instructions, set `strict: true` in `tsconfig`, and record the installed major versions in `docs/decisions.md`.

## Target structure

```
src/
  app/          providers, router, layout shell
  pages/        route components, thin
  features/     auth/  documents/  analysis/  chat/   (components, hooks, api calls per feature)
  components/ui/ shadcn components, unmodified except for tokens
  lib/          api.ts (single fetch client), utils.ts, env.ts
  styles/       tokens.css (design tokens from docs/design-system.md)
```

## Local development

The dev server proxies `/api` to `http://localhost:8000` so cookies stay same-origin, matching production (see ADR-008 in `docs/decisions.md`).
