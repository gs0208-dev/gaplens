import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  // Testing Library only cleans up on its own when test globals are on, and we keep them off.
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
