import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

import type { Chunk } from './schemas'

interface Props {
  chunks: Chunk[]
  /** The section a citation points at. It is marked and scrolled into view. */
  highlightedChunkId: string | null
}

/** The document as it was stored, section by section, for reading next to the chat. */
export function DocumentText({ chunks, highlightedChunkId }: Props) {
  const highlighted = useRef<HTMLElement>(null)

  useEffect(() => {
    // Missing in some test and old browser environments; the highlight still shows without it.
    highlighted.current?.scrollIntoView?.({ block: 'nearest' })
  }, [highlightedChunkId])

  if (chunks.length === 0) {
    return <p className="text-muted-foreground">This document has no text to show.</p>
  }

  return (
    <div className="space-y-4">
      {chunks.map((chunk) => {
        const isHighlighted = chunk.id === highlightedChunkId
        return (
          <section
            key={chunk.id}
            ref={isHighlighted ? highlighted : undefined}
            aria-current={isHighlighted ? 'true' : undefined}
            aria-label={chunk.section_label === null ? undefined : `Section ${chunk.section_label}`}
            className={cn(
              'border-l-2 border-transparent pl-3',
              isHighlighted && 'border-primary bg-accent',
            )}
          >
            {(chunk.section_label !== null || chunk.heading !== null) && (
              <p className="text-xs text-muted-foreground">
                {chunk.section_label !== null && (
                  <span className="font-mono text-foreground">{chunk.section_label}</span>
                )}
                {chunk.section_label !== null && chunk.heading !== null && ' · '}
                {chunk.heading}
                {chunk.page_start !== null && ` · page ${chunk.page_start}`}
              </p>
            )}
            <p className="max-w-prose text-base whitespace-pre-wrap">{chunk.content}</p>
          </section>
        )
      })}
    </div>
  )
}
