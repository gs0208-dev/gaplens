import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'

import { Form } from '@/components/ui/form'

import { EmailField, FormErrorSummary, PasswordField, SubmitButton, useServerError } from './fields'
import { useLogin } from './hooks'
import { loginFormSchema, type LoginFormValues } from './schemas'

export function LoginForm() {
  const login = useLogin()
  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginFormSchema),
    defaultValues: { email: '', password: '' },
  })
  const serverError = useServerError(form.setError)

  async function onSubmit(values: LoginFormValues) {
    serverError.clear()
    try {
      // On success the status changes and the router moves on. There is nothing to do here.
      await login.mutateAsync(values)
    } catch (error) {
      serverError.show(error)
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-6">
        {serverError.summary === null ? null : <FormErrorSummary error={serverError.summary} />}
        <EmailField control={form.control} />
        <PasswordField control={form.control} autoComplete="current-password" />
        <SubmitButton pending={form.formState.isSubmitting}>Sign in</SubmitButton>
      </form>
    </Form>
  )
}
