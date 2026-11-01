import { Info } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { ChatMessage } from './schemas'

interface Props {
  message: ChatMessage
  selectedChunkId: string | null
  onSelectCitation: (chunkId: string) => void
}

/** One message. Its text is always rendered as text, never as HTML. */
export function Message({ message, selectedChunkId, onSelectCitation }: Props) {
  if (message.role === 'user') {
    return (
      <li className="rounded-md bg-secondary p-3">
        <p className="text-xs text-muted-foreground">You</p>
        <p className="break-words whitespace-pre-wrap">{message.content}</p>
      </li>
    )
  }

  if (message.grounded === false) {
    // Not in the document: a neutral note, not an error and not an answer.
    return (
      <li>
        <div role="note" className="flex items-start gap-2 rounded-md border bg-secondary p-3">
          <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <p className="break-words whitespace-pre-wrap">{message.content}</p>
        </div>
      </li>
    )
  }

  return (
    <li className="space-y-2">
      <p className="text-xs text-muted-foreground">GapLens</p>
      <p className="break-words whitespace-pre-wrap">{message.content}</p>
      {message.citations.length > 0 && (
        <ol aria-label="Sources" className="space-y-1">
          {message.citations.map((citation, index) => {
            const selected = citation.chunk_id === selectedChunkId
            return (
              <li key={citation.chunk_id}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onSelectCitation(citation.chunk_id)}
                  className={cn(
                    'w-full rounded-md border p-2 text-left transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none',
                    selected && 'border-primary bg-accent',
                  )}
                >
                  <span className="text-xs font-medium">
                    Source {index + 1}
                    {citation.section_label !== null && (
                      <>
                        {' · section '}
                        <span className="font-mono">{citation.section_label}</span>
                      </>
                    )}
                  </span>
                  <span className="mt-1 line-clamp-3 block font-mono text-xs break-words text-muted-foreground">
                    {citation.quote}
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </li>
  )
}
