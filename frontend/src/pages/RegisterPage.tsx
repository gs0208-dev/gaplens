import { Link } from 'react-router'

import { RegisterForm } from '@/features/auth/RegisterForm'

export function RegisterPage() {
  return (
    <>
      <h1 className="mb-6 text-2xl font-semibold">Create an account</h1>
      <RegisterForm />
      <p className="mt-6 text-muted-foreground">
        Already have an account?{' '}
        <Link to="/login" className="text-primary underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </>
  )
}
