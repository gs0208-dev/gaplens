import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'

import { Form } from '@/components/ui/form'

import { EmailField, FormErrorSummary, PasswordField, SubmitButton, useServerError } from './fields'
import { useRegister } from './hooks'
import { registerFormSchema, type RegisterFormValues } from './schemas'

export function RegisterForm() {
  const register = useRegister()
  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(registerFormSchema),
    defaultValues: { email: '', password: '' },
  })
  const serverError = useServerError(form.setError)

  async function onSubmit(values: RegisterFormValues) {
    serverError.clear()
    try {
      // On success the user is signed in and the router moves on.
      await register.mutateAsync(values)
    } catch (error) {
      serverError.show(error)
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-6">
        {serverError.summary === null ? null : <FormErrorSummary error={serverError.summary} />}
        <EmailField control={form.control} />
        <PasswordField
          control={form.control}
          autoComplete="new-password"
          description="12 to 128 characters."
        />
        <SubmitButton pending={form.formState.isSubmitting}>Create account</SubmitButton>
      </form>
    </Form>
  )
}
