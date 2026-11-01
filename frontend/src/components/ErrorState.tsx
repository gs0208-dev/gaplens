import { CircleAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'

interface Props {
  message: string
  requestId?: string | null
  onRetry?: () => void
}

/** docs/design-system.md: what happened, what to do, the request id in small text, a retry. */
export function ErrorState({ message, requestId = null, onRetry }: Props) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-destructive p-4">
      <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-destructive" />
      <div className="space-y-2">
        <p>{message}</p>
        {requestId !== null && (
          <p className="text-xs text-muted-foreground">Request id: {requestId}</p>
        )}
        {onRetry !== undefined && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>
    </div>
  )
}
