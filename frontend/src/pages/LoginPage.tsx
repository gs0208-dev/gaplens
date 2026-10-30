import { Link } from 'react-router'

import { LoginForm } from '@/features/auth/LoginForm'

export function LoginPage() {
  return (
    <>
      <h1 className="mb-6 text-2xl font-semibold">Sign in</h1>
      <LoginForm />
      <p className="mt-6 text-muted-foreground">
        No account yet?{' '}
        <Link to="/register" className="text-primary underline underline-offset-4">
          Create an account
        </Link>
      </p>
    </>
  )
}
