import { Loader2, Send } from 'lucide-react'
import { useId, useState, type KeyboardEvent } from 'react'

import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import type { DocumentStatus } from '@/features/documents/schemas'

import { chatError, MAX_QUESTION_LENGTH, type ChatErrorView } from './errors'
import { useLatestThread, useSendQuestion, useThreadMessages } from './hooks'
import { Message } from './Message'

interface Props {
  documentId: string
  status: DocumentStatus
  selectedChunkId: string | null
  onSelectCitation: (chunkId: string) => void
}

interface Failure {
  view: ChatErrorView
  question: string
}

export function ChatPanel({ documentId, status, selectedChunkId, onSelectCitation }: Props) {
  const latest = useLatestThread(documentId)
  // undefined: the user has not chosen, so the last conversation is used. null: a new one.
  const [chosenThread, setChosenThread] = useState<string | null | undefined>(undefined)
  const threadId = chosenThread === undefined ? (latest.data ?? null) : chosenThread
  const history = useThreadMessages(threadId)
  const send = useSendQuestion(documentId)

  const [draft, setDraft] = useState('')
  const [asking, setAsking] = useState<string | null>(null)
  const [failure, setFailure] = useState<Failure | null>(null)
  const reasonId = useId()
  const counterId = useId()

  const ready = status === 'ready'
  const question = draft.trim()
  const tooLong = question.length > MAX_QUESTION_LENGTH
  const canSend = ready && !send.isPending && question.length > 0 && !tooLong

  function ask(text: string) {
    setFailure(null)
    setAsking(text)
    send.mutate(
      { question: text, threadId },
      {
        onSuccess: (reply) => {
          setChosenThread(reply.thread_id)
          setAsking(null)
        },
        onError: (error) => {
          const view = chatError(error)
          if (view.startNewThread) {
            setChosenThread(null)
          }
          setFailure({ view, question: text })
          setAsking(null)
        },
      },
    )
  }

  function submit() {
    if (!canSend) {
      return
    }
    setDraft('')
    ask(question)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  function startNewConversation() {
    setChosenThread(null)
    setFailure(null)
  }

  const loadingHistory = latest.isPending || (threadId !== null && history.isPending)
  const empty =
    !loadingHistory && history.messages.length === 0 && asking === null && failure === null

  return (
    <div className="flex min-h-96 flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">Chat</h2>
        {threadId !== null && (
          <Button variant="outline" size="sm" onClick={startNewConversation}>
            New conversation
          </Button>
        )}
      </div>

      <div
        role="log"
        aria-label="Conversation"
        aria-live="polite"
        className="flex-1 space-y-4 overflow-y-auto"
      >
        {loadingHistory && (
          <div role="status" aria-label="Loading the conversation" className="space-y-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}
        {latest.isError && (
          <ErrorState
            message="The previous conversation could not be loaded. You can still ask a new question."
            onRetry={() => void latest.refetch()}
          />
        )}
        {history.isError && (
          <ErrorState
            message="The conversation could not be loaded."
            onRetry={() => void history.refetch()}
          />
        )}
        {empty && (
          <p className="text-muted-foreground">
            Ask a question about this document. Answers cite the sections they come from.
          </p>
        )}
        <ol className="space-y-4">
          {history.messages.map((message) => (
            <Message
              key={message.id}
              message={message}
              selectedChunkId={selectedChunkId}
              onSelectCitation={onSelectCitation}
            />
          ))}
          {asking !== null && (
            <li className="rounded-md bg-secondary p-3">
              <p className="text-xs text-muted-foreground">You</p>
              <p className="break-words whitespace-pre-wrap">{asking}</p>
            </li>
          )}
        </ol>
        {asking !== null && (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <Loader2
              aria-hidden="true"
              className="size-4 animate-spin motion-reduce:animate-none"
            />
            Answering
          </p>
        )}
        {failure !== null && (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">Your question was not answered:</p>
            <p className="break-words whitespace-pre-wrap">{failure.question}</p>
            <ErrorState
              message={failure.view.message}
              requestId={failure.view.requestId}
              onRetry={() => ask(failure.question)}
            />
          </div>
        )}
      </div>

      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <label htmlFor="chat-question" className="sr-only">
          Question
        </label>
        <Textarea
          id="chat-question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!ready}
          rows={3}
          placeholder="Ask about this document"
          aria-describedby={ready ? counterId : reasonId}
          aria-invalid={tooLong}
        />
        <div className="flex items-center justify-between gap-2">
          {ready ? (
            <p
              id={counterId}
              className={tooLong ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}
            >
              {question.length} / {MAX_QUESTION_LENGTH}
            </p>
          ) : (
            <p id={reasonId} className="text-xs text-muted-foreground">
              Chat is available when the document is ready.
            </p>
          )}
          <Button type="submit" disabled={!canSend}>
            <Send aria-hidden="true" />
            Send
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Your question and the matching excerpts of the document are sent to Anthropic to write the
          answer.
        </p>
      </form>
    </div>
  )
}
