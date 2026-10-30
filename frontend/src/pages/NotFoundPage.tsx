import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <main className="mx-auto w-full max-w-form px-4 py-12">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-muted-foreground">Check the address, or go back to your documents.</p>
      <Link to="/documents" className="mt-6 inline-block text-primary underline underline-offset-4">
        Go to documents
      </Link>
    </main>
  )
}
