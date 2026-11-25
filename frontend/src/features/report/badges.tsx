import { CircleAlert, Info, TriangleAlert, type LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import type { Kind, Severity } from './schemas'

export const SEVERITY_LABELS: Record<Severity, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

export const SEVERITY_ICONS: Record<Severity, LucideIcon> = {
  high: CircleAlert,
  medium: TriangleAlert,
  low: Info,
}

const SEVERITY_CLASSES: Record<Severity, string> = {
  high: 'border-severity-high text-severity-high',
  medium: 'border-severity-medium text-severity-medium',
  low: 'border-severity-low text-severity-low',
}

// Written out in full so Tailwind finds the class names.
export const SEVERITY_TEXT: Record<Severity, string> = {
  high: 'text-severity-high',
  medium: 'text-severity-medium',
  low: 'text-severity-low',
}

export const KIND_LABELS: Record<Kind, string> = {
  missing: 'Missing',
  unclear: 'Unclear',
  contradiction: 'Contradiction',
}

/** Words and an icon, so color is never the only signal. */
export function SeverityBadge({ severity }: { severity: Severity }) {
  const Icon = SEVERITY_ICONS[severity]
  return (
    <Badge variant="outline" className={cn(SEVERITY_CLASSES[severity])}>
      <Icon aria-hidden="true" />
      {SEVERITY_LABELS[severity]}
    </Badge>
  )
}

export function KindBadge({ kind }: { kind: Kind }) {
  return <Badge variant="outline">{KIND_LABELS[kind]}</Badge>
}
