import { Navigate, Outlet } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { useAuthStore } from '@/features/auth/store'

/** Shown while the first refresh on page load is still answering. */
function PageSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="space-y-6">
      <Skeleton className="h-12 w-full rounded-none" />
      <div className="mx-auto w-full max-w-form space-y-4 px-4">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    </div>
  )
}

/** Pages that need a signed-in user. */
export function RequireAuth() {
  const status = useAuthStore((state) => state.status)
  if (status === 'unknown') {
    return <PageSkeleton />
  }
  return status === 'authenticated' ? <Outlet /> : <Navigate to="/login" replace />
}

/** Sign-in and register pages, which a signed-in user has no use for. */
export function GuestOnly() {
  const status = useAuthStore((state) => state.status)
  if (status === 'unknown') {
    return <PageSkeleton />
  }
  return status === 'authenticated' ? <Navigate to="/documents" replace /> : <Outlet />
}
