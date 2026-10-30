import { z } from 'zod'

// What the API returns. Checked at runtime, so a response in the wrong shape is an error.

export const userSchema = z.object({
  id: z.uuid(),
  email: z.string(),
  role: z.enum(['user', 'admin']),
  created_at: z.iso.datetime(),
})
export type User = z.infer<typeof userSchema>

export const userResponseSchema = z.object({ user: userSchema })

export const tokenResponseSchema = z.object({
  access_token: z.string(),
  expires_in: z.number(),
  user: userSchema,
})
export type TokenResponse = z.infer<typeof tokenResponseSchema>

// What the forms accept. These mirror the server rules in docs/api.md; the server checks again.

const emailField = z
  .string()
  .trim()
  .min(1, 'Enter your email address.')
  .pipe(z.email('Enter a valid email address.'))

export const loginFormSchema = z.object({
  email: emailField,
  // No minimum here: a wrong-length password just fails to match. The maximum matches the server.
  password: z.string().min(1, 'Enter your password.').max(128, 'Use at most 128 characters.'),
})
export type LoginFormValues = z.infer<typeof loginFormSchema>

export const registerFormSchema = z.object({
  email: emailField,
  password: z
    .string()
    .min(12, 'Use at least 12 characters.')
    .max(128, 'Use at most 128 characters.'),
})
export type RegisterFormValues = z.infer<typeof registerFormSchema>
