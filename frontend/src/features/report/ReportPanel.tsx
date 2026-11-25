import { Info, Loader2 } from 'lucide-react'
import { useId, useState } from 'react'

import { ErrorState } from '@/components/ErrorState'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { DocumentStatus } from '@/features/documents/schemas'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

import { KIND_LABELS, SEVERITY_ICONS, SEVERITY_LABELS, SEVERITY_TEXT } from './badges'
import { reportLoadError, startError } from './errors'
import { FindingRow, type SelectedQuote } from './FindingRow'
import { useLatestReport, useStartReport } from './hooks'
import { isRunning, type Analysis, type Kind, type Severity } from './schemas'

interface Props {
  documentId: string
  status: DocumentStatus
  selectedQuote: SelectedQuote | null
  onSelectQuote: (quote: SelectedQuote) => void
}

const SEVERITIES: Severity[] = ['high', 'medium', 'low']
const KINDS: Kind[] = ['missing', 'unclear', 'contradiction']

export function ReportPanel({ documentId, status, selectedQuote, onSelectQuote }: Props) {
  const ready = status === 'ready'
  const report = useLatestReport(documentId, ready)
  const start = useStartReport(documentId)
  const [confirming, setConfirming] = useState(false)

  function run() {
    setConfirming(false)
    start.mutate(undefined, {
      onError: (error) => {
        // Someone else (another tab) started one: show it instead of an error.
        if (error instanceof ApiError && error.code === 'analysis_already_running') {
          start.reset()
          void report.refetch()
        }
      },
    })
  }

  const analysis = report.data
  const startFailure = start.isError ? startError(start.error) : null

  let body
  if (!ready) {
    body = (
      <div className="space-y-3">
        <p className="text-muted-foreground">
          A report can be generated when the document is ready.
        </p>
        <Button disabled>Generate report</Button>
      </div>
    )
  } else if (report.isPending) {
    body = (
      <div role="status" aria-label="Loading the report" className="space-y-3">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    )
  } else if (report.isError) {
    body = <ErrorState {...reportLoadError(report.error)} onRetry={() => void report.refetch()} />
  } else if (analysis === null || analysis === undefined) {
    body = (
      <div className="space-y-3">
        <p className="text-muted-foreground">
          No report yet. A report lists what is missing, unclear or contradictory in this document,
          with quotes.
        </p>
        <Button onClick={run} disabled={start.isPending}>
          {start.isPending && (
            <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
          )}
          Generate report
        </Button>
      </div>
    )
  } else if (isRunning(analysis)) {
    body = (
      <p role="status" className="flex items-center gap-2 text-muted-foreground">
        <Loader2 aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
        Generating the report. This can take a few minutes.
      </p>
    )
  } else if (analysis.status === 'failed') {
    body = (
      <ErrorState
        message={analysis.error_message ?? 'The report could not be generated. Try again.'}
        onRetry={start.isPending ? undefined : run}
      />
    )
  } else {
    body = (
      <FinishedReport
        documentId={documentId}
        analysis={analysis}
        selectedQuote={selectedQuote}
        onSelectQuote={onSelectQuote}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">Report</h2>
        {analysis?.status === 'succeeded' && (
          <Button
            variant="outline"
            size="sm"
            disabled={start.isPending}
            onClick={() => setConfirming(true)}
          >
            Run again
          </Button>
        )}
      </div>
      {startFailure !== null && (
        <ErrorState
          message={startFailure.message}
          requestId={startFailure.requestId}
          onRetry={run}
        />
      )}
      {body}
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Run the report again?</AlertDialogTitle>
            <AlertDialogDescription>
              The new report replaces this one, including the review statuses you set.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={run}>Run again</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function droppedLine(count: number): string {
  return count === 1
    ? '1 more finding was removed because its quote could not be found in the document.'
    : `${count} more findings were removed because their quotes could not be found in the document.`
}

function emptiedNote(count: number): string {
  return count === 1
    ? 'No findings can be shown. The report suggested 1, but its quote could not be found in the document, so it was removed.'
    : `No findings can be shown. The report suggested ${count}, but their quotes could not be found in the document, so they were removed.`
}

function FinishedReport({
  documentId,
  analysis,
  selectedQuote,
  onSelectQuote,
}: {
  documentId: string
  analysis: Analysis
  selectedQuote: SelectedQuote | null
  onSelectQuote: (quote: SelectedQuote) => void
}) {
  const [severity, setSeverity] = useState<Severity | 'all'>('all')
  const [kind, setKind] = useState<Kind | 'all'>('all')
  const findings = analysis.findings
  const dropped = analysis.dropped_findings_count
  const shown = findings.filter(
    (f) => (severity === 'all' || f.severity === severity) && (kind === 'all' || f.kind === kind),
  )

  return (
    <div className="space-y-4">
      {analysis.summary !== null && (
        <p className="break-words whitespace-pre-wrap">{analysis.summary}</p>
      )}
      {findings.length === 0 ? (
        dropped === 0 ? (
          <p className="text-muted-foreground">The report found no gaps in this document.</p>
        ) : (
          <div role="note" className="flex items-start gap-2 rounded-md border bg-secondary p-3">
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <p>{emptiedNote(dropped)}</p>
          </div>
        )
      ) : (
        <>
          <div className="space-y-1">
            <ul aria-label="Findings by severity" className="flex flex-wrap gap-4">
              {SEVERITIES.map((level) => {
                const Icon = SEVERITY_ICONS[level]
                const count = findings.filter((f) => f.severity === level).length
                return (
                  <li key={level} className={cn('flex items-center gap-1', SEVERITY_TEXT[level])}>
                    <Icon aria-hidden="true" className="size-4" />
                    {count} {SEVERITY_LABELS[level].toLowerCase()}
                  </li>
                )
              })}
            </ul>
            {dropped > 0 && <p className="text-xs text-muted-foreground">{droppedLine(dropped)}</p>}
          </div>
          <div className="flex flex-wrap gap-6">
            <FilterGroup
              label="Severity"
              options={SEVERITIES}
              labels={SEVERITY_LABELS}
              value={severity}
              onChange={setSeverity}
            />
            <FilterGroup
              label="Kind"
              options={KINDS}
              labels={KIND_LABELS}
              value={kind}
              onChange={setKind}
            />
          </div>
          {shown.length === 0 ? (
            <div className="space-y-2">
              <p className="text-muted-foreground">No findings match these filters.</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSeverity('all')
                  setKind('all')
                }}
              >
                Clear filters
              </Button>
            </div>
          ) : (
            <ul aria-label="Findings" className="border-t">
              {shown.map((finding) => (
                <FindingRow
                  key={finding.id}
                  documentId={documentId}
                  finding={finding}
                  selectedQuote={selectedQuote}
                  onSelectQuote={onSelectQuote}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

function FilterGroup<T extends string>({
  label,
  options,
  labels,
  value,
  onChange,
}: {
  label: string
  options: T[]
  labels: Record<T, string>
  value: T | 'all'
  onChange: (value: T | 'all') => void
}) {
  const labelId = useId()
  const choices: (T | 'all')[] = ['all', ...options]
  return (
    <div className="space-y-1">
      <p id={labelId} className="text-xs font-medium text-muted-foreground">
        {label}
      </p>
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {choices.map((choice) => (
          <Button
            key={choice}
            variant="outline"
            size="sm"
            aria-pressed={value === choice}
            className={cn(value === choice && 'border-primary bg-accent')}
            onClick={() => onChange(choice)}
          >
            {choice === 'all' ? 'All' : labels[choice]}
          </Button>
        ))}
      </div>
    </div>
  )
}
