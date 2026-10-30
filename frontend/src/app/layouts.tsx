import { LogOut } from 'lucide-react'
import { Outlet } from 'react-router'

import { Button } from '@/components/ui/button'
import { useCurrentUser, useLogout } from '@/features/auth/hooks'

/** Sign-in and register: one column, product name as text, no illustration. */
export function AuthLayout() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-form flex-col justify-center px-4 py-12">
      <p className="mb-8 text-xl font-semibold">GapLens</p>
      <Outlet />
    </main>
  )
}

/** Signed-in pages: a 48 px top bar and the content below it. */
export function AppLayout() {
  const user = useCurrentUser()
  const logout = useLogout()

  return (
    <div className="min-h-screen">
      <header className="flex h-12 items-center justify-between border-b border-border bg-surface px-4">
        <span className="font-semibold">GapLens</span>
        <div className="flex items-center gap-4">
          <span className="text-muted-foreground">{user?.email}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            <LogOut aria-hidden="true" />
            Sign out
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-content px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
