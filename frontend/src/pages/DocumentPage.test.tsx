import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { problem, stubApi, type FakeResponse } from '@/test/fetch'
import { chunk, citation, documentDetails, message, SIGNED_IN } from '@/test/fixtures'
import { renderApp, resetClientState } from '@/test/render'

beforeEach(resetClientState)
afterEach(() => vi.useRealTimers())

const ID = 'doc-1'
const DOCUMENT = `GET /api/v1/documents/${ID}`
const CHUNKS = `GET /api/v1/documents/${ID}/chunks`
const THREADS = `GET /api/v1/documents/${ID}/threads?limit=1`
const CHAT = `POST /api/v1/documents/${ID}/chat`
const messagesOf = (thread: string) => `GET /api/v1/threads/${thread}/messages?limit=100`

type Routes = Parameters<typeof stubApi>[0]

const NO_THREADS = () => ({ body: { items: [], next_cursor: null } })
const threadList = (id: string) => () => ({
  body: {
    items: [
      {
        id,
        title: 'earlier',
        created_at: '2026-11-01T09:00:00Z',
        updated_at: '2026-11-01T09:05:00Z',
      },
    ],
    next_cursor: null,
  },
})
const page = (...items: Record<string, unknown>[]): FakeResponse => ({
  body: { items, next_cursor: null },
})

const REFUND = chunk({
  id: 'chunk-a',
  section_label: '3.1-3.5',
  heading: 'Refund handling',
  page_start: 2,
})
const ESCALATION = chunk({
  id: 'chunk-b',
  chunk_index: 1,
  section_label: '5.1-5.4',
  heading: 'Quality and review',
  content: '5.3 To limit fraud exposure, L1 agents may approve refunds only up to INR 2,500.',
  page_start: 3,
})

function readyDocument(routes: Routes = {}): Routes {
  return {
    [DOCUMENT]: () => ({ body: { document: documentDetails({ id: ID, title: 'Refund SOP' }) } }),
    [CHUNKS]: () => ({ body: { items: [REFUND, ESCALATION] } }),
    [THREADS]: NO_THREADS,
    ...routes,
  }
}

async function openWorkspace(routes: Routes) {
  const fake = stubApi({ ...SIGNED_IN, ...routes })
  const rendered = renderApp(`/documents/${ID}`)
  return { fake, ...rendered }
}

async function openReady(routes: Routes = {}) {
  const opened = await openWorkspace(readyDocument(routes))
  await screen.findByRole('heading', { name: 'Refund SOP' })
  return opened
}

async function ask(user: Awaited<ReturnType<typeof openReady>>['user'], text: string) {
  await user.type(screen.getByLabelText('Question'), text)
  await user.click(screen.getByRole('button', { name: 'Send' }))
}

describe('the workspace', () => {
  it('shows the title, the status in words and the document text by section', async () => {
    await openReady()

    expect(screen.getByText('Ready')).toBeInTheDocument()
    const section = (
      await screen.findByText(/L1 agents may approve refunds up to INR 5,000/)
    ).closest('section')
    expect(section).toHaveAttribute('aria-label', 'Section 3.1-3.5')
    expect(section).toHaveTextContent('Refund handling')
    expect(section).toHaveTextContent('page 2')
    expect(screen.getByText(/only up to INR 2,500/).closest('section')).toHaveAttribute(
      'aria-label',
      'Section 5.1-5.4',
    )
    expect(screen.getByRole('link', { name: 'Documents' })).toHaveAttribute('href', '/documents')
  })

  it('shows a skeleton while the document loads', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    await openWorkspace(
      readyDocument({
        [DOCUMENT]: async () => {
          await gate
          return { body: { document: documentDetails({ id: ID, title: 'Refund SOP' }) } }
        },
      }),
    )

    expect(await screen.findByRole('status', { name: 'Loading the document' })).toBeInTheDocument()
    release()
    expect(await screen.findByRole('heading', { name: 'Refund SOP' })).toBeInTheDocument()
  })

  it('says so when the document does not exist or was deleted', async () => {
    await openWorkspace({ [DOCUMENT]: () => problem(404, 'document_not_found', 'No document.') })

    expect(await screen.findByRole('heading', { name: 'Document not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Documents' })).toBeInTheDocument()
  })

  it('shows another failure with the request id and tries again on request', async () => {
    let calls = 0
    const { user } = await openWorkspace(
      readyDocument({
        [DOCUMENT]: () => {
          calls += 1
          return calls === 1
            ? problem(500, 'internal_error', 'Server wording.')
            : { body: { document: documentDetails({ id: ID, title: 'Refund SOP' }) } }
        },
      }),
    )

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Request id: req-12345678')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { name: 'Refund SOP' })).toBeInTheDocument()
  })

  it('shows the text error with a retry when the sections cannot be loaded', async () => {
    let calls = 0
    const { user } = await openReady({
      [CHUNKS]: () => {
        calls += 1
        return calls === 1 ? problem(500, 'internal_error', 'x') : { body: { items: [REFUND] } }
      },
    })

    await user.click(await screen.findByRole('button', { name: 'Try again' }))

    expect(await screen.findByText(/up to INR 5,000 per request/)).toBeInTheDocument()
  })

  it('waits for a document that is processing, without asking for its text, and turns on chat when it is ready', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let calls = 0
    const { fake } = await openWorkspace(
      readyDocument({
        [DOCUMENT]: () => {
          calls += 1
          const status = calls < 2 ? 'processing' : 'ready'
          return { body: { document: documentDetails({ id: ID, title: 'Refund SOP', status }) } }
        },
      }),
    )

    expect(await screen.findByText('Processing')).toBeInTheDocument()
    expect(screen.getByText(/appears here when it is ready/)).toBeInTheDocument()
    expect(screen.getByLabelText('Question')).toBeDisabled()
    expect(screen.getByText('Chat is available when the document is ready.')).toBeInTheDocument()
    expect(fake.to('/chunks')).toHaveLength(0)

    await vi.advanceTimersByTimeAsync(2000)

    expect(await screen.findByText(/up to INR 5,000 per request/)).toBeInTheDocument()
    expect(screen.getByLabelText('Question')).toBeEnabled()
  })

  it('shows why a failed document has no text, and keeps chat off', async () => {
    const { fake } = await openWorkspace(
      readyDocument({
        [DOCUMENT]: () => ({
          body: {
            document: documentDetails({
              id: ID,
              title: 'Broken',
              status: 'failed',
              error_message: 'This document could not be processed. Upload it again.',
            }),
          },
        }),
      }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This document could not be processed. Upload it again.',
    )
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByLabelText('Question')).toBeDisabled()
    expect(fake.to('/chunks')).toHaveLength(0)
  })
})

describe('the chat', () => {
  it('invites a first question when there is no conversation yet', async () => {
    await openReady()

    expect(await screen.findByText(/Ask a question about this document/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New conversation' })).not.toBeInTheDocument()
    expect(screen.getByText(/sent to Anthropic/)).toBeInTheDocument()
  })

  it('brings back the last conversation with its sources', async () => {
    const earlier = [
      message({ id: 'm1', role: 'user', content: 'What is the L1 limit?', grounded: null }),
      message({ id: 'm2', content: 'It is INR 5,000.', citations: [citation()] }),
    ]
    await openReady({
      [THREADS]: threadList('t-old'),
      [messagesOf('t-old')]: () => page(...earlier),
    })

    expect(await screen.findByText('What is the L1 limit?')).toBeInTheDocument()
    expect(screen.getByText('It is INR 5,000.')).toBeInTheDocument()
    const sources = screen.getByRole('list', { name: 'Sources' })
    expect(sources).toHaveTextContent('Source 1')
    expect(sources).toHaveTextContent('3.1-3.5')
    expect(screen.getByRole('button', { name: 'New conversation' })).toBeInTheDocument()
  })

  it('sends a question, shows it while the answer is written, then shows the answer with its sources', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const reply = message({ id: 'a1', content: 'Up to INR 5,000.', citations: [citation()] })
    let stored: Record<string, unknown>[] = []
    const { user, fake } = await openReady({
      [CHAT]: async () => {
        await gate
        stored = [
          message({ id: 'u1', role: 'user', content: 'What is the limit?', grounded: null }),
          reply,
        ]
        return { body: { thread_id: 't-new', message: reply } }
      },
      [messagesOf('t-new')]: () => page(...stored),
    })

    await ask(user, 'What is the limit?')

    expect(await screen.findByRole('status', { name: '' })).toHaveTextContent('Answering')
    expect(screen.getByText('What is the limit?')).toBeInTheDocument()
    expect(screen.getByLabelText('Question')).toHaveValue('')
    expect(fake.to('/chat')[0]?.body).toEqual({ question: 'What is the limit?' })
    release()

    expect(await screen.findByText('Up to INR 5,000.')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Sources' })).toHaveTextContent('3.1-3.5')
    expect(screen.queryByText('Answering')).not.toBeInTheDocument()
  })

  it('keeps the conversation going in the same thread', async () => {
    const stored: Record<string, unknown>[] = []
    const { user, fake } = await openReady({
      [CHAT]: (request) => {
        const body = request.body as { question: string }
        const reply = message({
          id: `a${stored.length}`,
          content: `Answer to ${body.question}`,
          citations: [],
        })
        stored.push(
          message({
            id: `u${stored.length}`,
            role: 'user',
            content: body.question,
            grounded: null,
          }),
          reply,
        )
        return { body: { thread_id: 't-1', message: reply } }
      },
      [messagesOf('t-1')]: () => page(...stored),
    })

    await ask(user, 'first')
    await screen.findByText('Answer to first')
    await ask(user, 'second')
    await screen.findByText('Answer to second')

    const sent = fake.to('/chat').map((r) => r.body)
    expect(sent).toEqual([{ question: 'first' }, { question: 'second', thread_id: 't-1' }])
  })

  it('sends on Enter and adds a line on Shift+Enter', async () => {
    const reply = message({ content: 'ok' })
    const { user, fake } = await openReady({
      [CHAT]: () => ({ body: { thread_id: 't-1', message: reply } }),
      [messagesOf('t-1')]: () => page(reply),
    })
    const box = screen.getByLabelText('Question')

    await user.type(box, 'line one{Shift>}{Enter}{/Shift}line two')
    expect(fake.to('/chat')).toHaveLength(0)
    expect(box).toHaveValue('line one\nline two')
    await user.keyboard('{Enter}')

    await waitFor(() => expect(fake.to('/chat')).toHaveLength(1))
    expect(fake.to('/chat')[0]?.body).toEqual({ question: 'line one\nline two' })
  })

  it('does not send an empty question and counts the length', async () => {
    const { user, fake } = await openReady()
    const send = screen.getByRole('button', { name: 'Send' })

    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('Question'), '   ')
    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('Question'), 'abc')

    expect(screen.getByText('3 / 1000')).toBeInTheDocument()
    expect(send).toBeEnabled()
    expect(fake.to('/chat')).toHaveLength(0)
  })

  it('refuses a question over 1000 characters', async () => {
    const { user } = await openReady()

    await user.click(screen.getByLabelText('Question'))
    await user.paste('x'.repeat(1001))

    expect(screen.getByText('1001 / 1000')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(screen.getByLabelText('Question')).toBeInvalid()
  })

  it('starts a fresh conversation on request', async () => {
    const earlier = [
      message({ id: 'm1', role: 'user', content: 'Old question', grounded: null }),
      message({ id: 'm2' }),
    ]
    const reply = message({ id: 'n2', content: 'New answer.' })
    const { user, fake } = await openReady({
      [THREADS]: threadList('t-old'),
      [messagesOf('t-old')]: () => page(...earlier),
      [CHAT]: () => ({ body: { thread_id: 't-fresh', message: reply } }),
      [messagesOf('t-fresh')]: () => page(reply),
    })
    await screen.findByText('Old question')

    await user.click(screen.getByRole('button', { name: 'New conversation' }))

    expect(screen.queryByText('Old question')).not.toBeInTheDocument()
    expect(await screen.findByText(/Ask a question about this document/)).toBeInTheDocument()
    await ask(user, 'Something else')
    await screen.findByText('New answer.')
    expect(fake.to('/chat')[0]?.body).toEqual({ question: 'Something else' })
  })
})

describe('answers and sources', () => {
  async function withAnswer(content: string, extras: Record<string, unknown> = {}) {
    const reply = message({ id: 'a1', content, ...extras })
    return openReady({
      [THREADS]: threadList('t-1'),
      [messagesOf('t-1')]: () =>
        page(message({ id: 'u1', role: 'user', content: 'Q', grounded: null }), reply),
    })
  }

  it('marks the section a source points to, and moves the mark to the next source', async () => {
    const { user } = await withAnswer('Two limits.', {
      citations: [
        citation({ chunk_id: 'chunk-a' }),
        citation({
          chunk_id: 'chunk-b',
          section_label: '5.1-5.4',
          quote: '5.3 To limit fraud exposure',
        }),
      ],
    })
    const [first, second] = await screen.findAllByRole('button', { name: /Source \d/ })
    const sectionA = screen
      .getByText(/up to INR 5,000 per request/, { selector: 'p' })
      .closest('section')
    const sectionB = screen.getByText(/only up to INR 2,500/).closest('section')

    await user.click(first as HTMLElement)

    expect(sectionA).toHaveAttribute('aria-current', 'true')
    expect(sectionB).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('button', { name: /Source 1/, hidden: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    await user.click(screen.getByRole('button', { name: /Source 2/, hidden: true }))

    expect(sectionB).toHaveAttribute('aria-current', 'true')
    expect(sectionA).not.toHaveAttribute('aria-current')
    expect(second).toBeDefined()
  })

  it('scrolls the marked section into view', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    const { user } = await withAnswer('One limit.', {
      citations: [citation({ chunk_id: 'chunk-b' })],
    })

    await user.click(await screen.findByRole('button', { name: /Source 1/ }))

    await waitFor(() => expect(scroll).toHaveBeenCalled())
    // @ts-expect-error cleaning up the stub that was added for this test
    delete Element.prototype.scrollIntoView
  })

  it('switches to the document tab when a source is chosen, for narrow screens', async () => {
    const { user } = await withAnswer('One limit.', {
      citations: [citation({ chunk_id: 'chunk-a' })],
    })
    expect(await screen.findByRole('tab', { name: 'Chat' })).toHaveAttribute(
      'aria-selected',
      'true',
    )

    await user.click(screen.getByRole('button', { name: /Source 1/ }))

    expect(screen.getByRole('tab', { name: 'Document' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows an answer that is not in the document as a neutral note', async () => {
    await withAnswer('This is not found in the document.', { grounded: false })

    const note = await screen.findByRole('note')
    expect(note).toHaveTextContent('This is not found in the document.')
    expect(screen.queryByRole('list', { name: 'Sources' })).not.toBeInTheDocument()
  })

  it('shows text from the model as text, never as HTML', async () => {
    const hostile = '<img src=x onerror="alert(1)"> and <b>bold</b>'
    await withAnswer(hostile, {
      citations: [citation({ quote: '<script>alert(2)</script>' })],
    })

    expect(await screen.findByText(hostile)).toBeInTheDocument()
    expect(document.body.querySelector('img')).toBeNull()
    expect(document.body.querySelector('b')).toBeNull()
    expect(document.body.querySelector('script')).toBeNull()
    expect(screen.getByText('<script>alert(2)</script>')).toBeInTheDocument()
  })
})

describe('when a question fails', () => {
  it.each([
    [
      409,
      'document_not_ready',
      'This document is still being processed. Try again when it is ready.',
    ],
    [503, 'llm_unavailable', 'Answers are not available right now. Try again later.'],
    [503, 'llm_timeout', 'The answer took too long. Try again.'],
    [503, 'llm_invalid_output', 'An answer could not be produced. Try again.'],
    [404, 'document_not_found', 'This document no longer exists.'],
  ])('explains %s %s and offers to try again', async (status, code, expected) => {
    const reply = message({ content: 'Fine now.' })
    let calls = 0
    const { user, fake } = await openReady({
      [CHAT]: () => {
        calls += 1
        return calls === 1
          ? problem(status, code, 'Server wording.')
          : { body: { thread_id: 't-1', message: reply } }
      },
      [messagesOf('t-1')]: () => page(reply),
    })

    await ask(user, 'Will this work?')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(expected)
    expect(alert).toHaveTextContent('Request id: req-12345678')
    expect(alert).not.toHaveTextContent('Server wording')
    expect(screen.getByText('Will this work?')).toBeInTheDocument()

    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Fine now.')).toBeInTheDocument()
    expect(fake.to('/chat').map((r) => r.body)).toEqual([
      { question: 'Will this work?' },
      { question: 'Will this work?' },
    ])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says how long to wait when the question limit is reached', async () => {
    const { user } = await openReady({
      [CHAT]: () => ({ ...problem(429, 'rate_limited', 'x'), headers: { 'Retry-After': '1800' } }),
    })

    await ask(user, 'One more')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You have asked too many questions. Try again in 30 minutes.',
    )
  })

  it('starts a new conversation when the saved one has disappeared', async () => {
    const reply = message({ id: 'a9', content: 'Answered in a new thread.' })
    let calls = 0
    const { user, fake } = await openReady({
      [THREADS]: threadList('t-gone'),
      [messagesOf('t-gone')]: () =>
        page(message({ id: 'm1', role: 'user', content: 'Old', grounded: null })),
      [CHAT]: () => {
        calls += 1
        return calls === 1
          ? problem(404, 'thread_not_found', 'x')
          : { body: { thread_id: 't-2', message: reply } }
      },
      [messagesOf('t-2')]: () => page(reply),
    })
    await screen.findByText('Old')

    await ask(user, 'Anything')
    expect(await screen.findByRole('alert')).toHaveTextContent('start a new one')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Answered in a new thread.')).toBeInTheDocument()
    expect(fake.to('/chat').map((r) => r.body)).toEqual([
      { question: 'Anything', thread_id: 't-gone' },
      { question: 'Anything' },
    ])
  })

  it('shows the conversation error with a retry when it cannot be loaded', async () => {
    let calls = 0
    const { user } = await openReady({
      [THREADS]: threadList('t-1'),
      [messagesOf('t-1')]: () => {
        calls += 1
        return calls === 1
          ? problem(500, 'internal_error', 'x')
          : page(message({ content: 'Back again.' }))
      },
    })

    const alert = await screen.findByText('The conversation could not be loaded.')
    await user.click(
      within(alert.closest('[role="alert"]') as HTMLElement).getByRole('button', {
        name: 'Try again',
      }),
    )

    expect(await screen.findByText('Back again.')).toBeInTheDocument()
  })
})
