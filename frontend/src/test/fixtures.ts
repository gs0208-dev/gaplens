import { tokenResponse } from './fetch'

/** Routes every signed-in screen test needs: the page load restores the session. */
export const SIGNED_IN = { 'POST /api/v1/auth/refresh': () => tokenResponse() }

let counter = 0
function nextId(prefix: string): string {
  counter += 1
  return `${prefix}-${counter}`
}

export function documentSummary(overrides: Record<string, unknown> = {}) {
  return {
    id: nextId('doc'),
    title: 'Refund SOP',
    status: 'ready',
    page_count: 3,
    chunk_count: 8,
    created_at: '2026-11-01T09:30:00Z',
    ...overrides,
  }
}

export function documentDetails(overrides: Record<string, unknown> = {}) {
  return {
    ...documentSummary(),
    filename: 'sop.pdf',
    mime_type: 'application/pdf',
    size_bytes: 1200,
    error_message: null,
    ...overrides,
  }
}

export function chunk(overrides: Record<string, unknown> = {}) {
  return {
    id: nextId('chunk'),
    chunk_index: 0,
    section_label: '3.1-3.5',
    heading: 'Refund handling',
    content: '3.1 L1 agents may approve refunds up to INR 5,000 per request.',
    page_start: 2,
    ...overrides,
  }
}

export function message(overrides: Record<string, unknown> = {}) {
  return {
    id: nextId('message'),
    role: 'assistant',
    content: 'L1 agents may approve refunds up to INR 5,000.',
    grounded: true,
    citations: [],
    created_at: '2026-11-01T09:31:00Z',
    ...overrides,
  }
}

export function citation(overrides: Record<string, unknown> = {}) {
  return {
    chunk_id: 'chunk-a',
    section_label: '3.1-3.5',
    quote: '3.1 L1 agents may approve refunds up to INR 5,000 per request.',
    ...overrides,
  }
}
