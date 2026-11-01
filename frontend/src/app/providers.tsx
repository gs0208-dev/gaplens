import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { TooltipProvider } from '@/components/ui/tooltip'
import { connectSession } from '@/features/auth/session'
import { queryClient } from '@/lib/query-client'

// Runs once when the module loads, before any component can make a request.
connectSession()

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  )
}
