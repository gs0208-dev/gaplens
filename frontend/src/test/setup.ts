import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { unplannedRequests } from './fetch'

// jsdom has no ResizeObserver, which Radix menus and popovers use to place themselves. A no-op is
// enough: layout is not something jsdom can check anyway.
class NoopResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = NoopResizeObserver

afterEach(() => {
  // Testing Library only cleans up on its own when test globals are on, and we keep them off.
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  if (unplannedRequests.length > 0) {
    const requests = unplannedRequests.splice(0).join(', ')
    throw new Error(`The test made requests it did not plan for: ${requests}`)
  }
})
