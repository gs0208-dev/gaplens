import { CircleAlert, Loader2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { Control, UseFormSetError } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'

import { describeError, type DescribedError } from './errors'

export interface CredentialFields {
  email: string
  password: string
}

export function EmailField({ control }: { control: Control<CredentialFields> }) {
  return (
    <FormField
      control={control}
      name="email"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Email</FormLabel>
          <FormControl>
            <Input type="email" autoComplete="email" {...field} />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  )
}

interface PasswordFieldProps {
  control: Control<CredentialFields>
  autoComplete: 'current-password' | 'new-password'
  description?: string
}

export function PasswordField({ control, autoComplete, description }: PasswordFieldProps) {
  return (
    <FormField
      control={control}
      name="password"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Password</FormLabel>
          <FormControl>
            <Input type="password" autoComplete={autoComplete} {...field} />
          </FormControl>
          {description === undefined ? null : <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  )
}

/** What went wrong with the whole submit, in words, with the request id for support. */
export function FormErrorSummary({ error }: { error: DescribedError }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive bg-surface p-3"
    >
      <CircleAlert className="size-5 shrink-0 text-destructive" aria-hidden="true" />
      <div className="space-y-1">
        <p className="leading-5">{error.message}</p>
        {error.requestId === null ? null : (
          <p className="font-mono text-xs text-muted-foreground">Request ID: {error.requestId}</p>
        )}
      </div>
    </div>
  )
}

export function SubmitButton({ pending, children }: { pending: boolean; children: ReactNode }) {
  return (
    <Button type="submit" className="w-full" disabled={pending}>
      {pending ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
      {children}
    </Button>
  )
}

/**
 * Keeps the error summary for a form and puts field-level server errors on their fields.
 * A duplicate email, for example, shows under the email input, not in the summary.
 */
export function useServerError(setError: UseFormSetError<CredentialFields>) {
  const [summary, setSummary] = useState<DescribedError | null>(null)

  function show(error: unknown): void {
    const described = describeError(error)
    if (described.fieldErrors.email !== undefined) {
      setError(
        'email',
        { type: 'server', message: described.fieldErrors.email },
        { shouldFocus: true },
      )
    }
    if (described.fieldErrors.password !== undefined) {
      setError('password', { type: 'server', message: described.fieldErrors.password })
    }
    setSummary(described.message === null ? null : described)
  }

  return { summary, show, clear: () => setSummary(null) }
}
