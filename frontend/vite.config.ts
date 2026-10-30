import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Where the backend listens. Only change it when port 8000 is busy: API_PROXY_TARGET=... make frontend-dev
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  server: {
    // Same-origin API in development, as in production (ADR-008). The refresh cookie is then
    // first-party and the browser sends the page's own origin, which the backend checks.
    proxy: { '/api': apiTarget },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
