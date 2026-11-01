import { CircleAlert, CircleCheck, Loader2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import type { DocumentStatus } from './schemas'

const LABELS: Record<DocumentStatus, string> = {
  uploaded: 'Queued',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
}

/** The status is always words plus an icon, so color is never the only signal. */
export function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        status === 'ready' && 'border-success text-success',
        status === 'failed' && 'border-destructive text-destructive',
      )}
    >
      {status === 'ready' && <CircleCheck aria-hidden="true" />}
      {status === 'failed' && <CircleAlert aria-hidden="true" />}
      {(status === 'uploaded' || status === 'processing') && (
        <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
      )}
      {LABELS[status]}
    </Badge>
  )
}
