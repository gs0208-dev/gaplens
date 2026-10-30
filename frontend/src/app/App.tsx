import type { createBrowserRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'

import { useSessionRestore } from '@/features/auth/hooks'

type AppRouter = ReturnType<typeof createBrowserRouter>

export function App({ router }: { router: AppRouter }) {
  useSessionRestore()
  return <RouterProvider router={router} />
}
