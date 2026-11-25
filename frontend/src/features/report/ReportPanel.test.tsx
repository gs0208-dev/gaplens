import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { problem, stubApi, type FakeResponse } from '@/test/fetch'
import { analysis, chunk, documentDetails, finding, SIGNED_IN } from '@/test/fixtures'
import { renderApp, resetClientState } from '@/test/render'

beforeEach(resetClientState)
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const ID = 'doc-1'
const DOCUMENT = `GET /api/v1/documents/${ID}`
const CHUNKS = `GET /api/v1/documents/${ID}/chunks`
const THREADS = `GET /api/v1/documents/${ID}/threads?limit=1`
const LATEST = `GET /api/v1/documents/${ID}/analyses/latest`
const START = `POST /api/v1/documents/${ID}/analyses`
const patchOf = (findingId: string) => `PATCH /api/v1/findings/${findingId}`

type Routes = Parameters<typeof stubApi>[0]

const REFUND = chunk({
  id: 'chunk-a',
  section_label: '3.1-3.5',
  content: '3.1 L1 agents may approve refunds up to INR 5,000 per request. 3.2 Above that, ask L2.',
})
const QUALITY = chunk({
  id: 'chunk-b',
  chunk_index: 1,
  section_label: '5.1-5.4',
  heading: 'Quality and review',
  content: '5.3 To limit fraud exposure, L1 agents may approve refunds only up to INR 2,500.',
})

const CONFLICT = finding({
  id: 'f-conflict',
  kind: 'contradiction',
  severity: 'high',
  title: 'Refund limit differs between sections',
  citations: [
    { chunk_id: 'chunk-a', section_label: '3.1-3.5', quote: 'refunds up to INR 5,000 per request' },
    { chunk_id: 'chunk-b', section_label: '5.1-5.4', quote: 'only up to INR 2,500' },
  ],
})
const OWNER = finding({
  id: 'f-owner',
  kind: 'missing',
  severity: 'medium',
  title: 'No owner for refund disputes',
  description: 'The document does not say who handles a disputed refund.',
  suggested_question: 'Who owns a refund dispute?',
})
const WORDING = finding({
  id: 'f-wording',
  kind: 'unclear',
  severity: 'low',
  title: 'L2 is not defined',
  citations: [{ chunk_id: 'chunk-a', section_label: '3.1-3.5', quote: 'Above that, ask L2.' }],
})

const report = (overrides: Record<string, unknown> = {}): FakeResponse => ({
  body: {
    analysis: analysis({
      findings: [CONFLICT, OWNER, WORDING],
      findings_count: 3,
      ...overrides,
    }),
  },
})

function routes(extra: Routes = {}): Routes {
  return {
    ...SIGNED_IN,
    [DOCUMENT]: () => ({ body: { document: documentDetails({ id: ID, title: 'Refund SOP' }) } }),
    [CHUNKS]: () => ({ body: { items: [REFUND, QUALITY] } }),
    [THREADS]: () => ({ body: { items: [], next_cursor: null } }),
    [LATEST]: () => report(),
    ...extra,
  }
}

async function open(extra: Routes = {}) {
  const fake = stubApi(routes(extra))
  const rendered = renderApp(`/documents/${ID}`)
  await screen.findByRole('heading', { name: 'Refund SOP' })
  return { fake, ...rendered }
}

function findingsList() {
  return screen.getByRole('list', { name: 'Findings' })
}

async function expand(user: Awaited<ReturnType<typeof open>>['user'], title: string) {
  await user.click(await screen.findByRole('button', { name: new RegExp(title) }))
}

describe('the report tab', () => {
  it('is the tab shown first', async () => {
    await open()

    expect(screen.getByRole('tab', { name: 'Report' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByRole('heading', { name: 'Report' })).toBeInTheDocument()
  })

  it('shows the summary, the counts by severity in words and the findings in API order', async () => {
    await open()

    expect(
      await screen.findByText('A short refund SOP with two conflicting limits.'),
    ).toBeInTheDocument()
    const counts = screen.getByRole('list', { name: 'Findings by severity' })
    expect(counts).toHaveTextContent('1 high')
    expect(counts).toHaveTextContent('1 medium')
    expect(counts).toHaveTextContent('1 low')
    const rows = within(findingsList()).getAllByRole('button', { expanded: false })
    expect(rows.map((row) => row.textContent)).toEqual([
      'HighContradictionRefund limit differs between sections',
      'MediumMissingNo owner for refund disputes',
      'LowUnclearL2 is not defined',
    ])
  })

  it('expands a finding to its description, evidence, question and status', async () => {
    const { user } = await open()

    await expand(user, 'Refund limit differs')

    const row = screen.getByRole('button', { name: /Refund limit differs/ })
    expect(row).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/allows INR 5,000 while 5.3 caps it/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /refunds up to INR 5,000 per request/ }),
    ).toHaveTextContent('Section 3.1-3.5')
    expect(screen.getByText('Which refund limit applies to L1 agents?')).toBeInTheDocument()
    const status = screen.getByRole('group', { name: 'Review status' })
    expect(within(status).getByRole('button', { name: 'Open' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('says a missing finding has no quote', async () => {
    const { user } = await open()

    await expand(user, 'No owner for refund disputes')

    expect(screen.getByText(/No quote: this finding is about something/)).toBeInTheDocument()
  })

  it('marks the exact quoted words in the document when a quote is chosen', async () => {
    const { user } = await open()
    await expand(user, 'Refund limit differs')

    await user.click(screen.getByRole('button', { name: /only up to INR 2,500/ }))

    const section = screen.getByRole('region', { name: 'Section 5.1-5.4' })
    expect(section).toHaveAttribute('aria-current', 'true')
    const mark = section.querySelector('mark')
    expect(mark).toHaveTextContent(/^only up to INR 2,500$/)
    expect(screen.getByRole('tab', { name: 'Document' })).toHaveAttribute('aria-selected', 'true')
  })

  it('moves the mark to the next quote', async () => {
    const { user } = await open()
    await expand(user, 'Refund limit differs')
    await user.click(screen.getByRole('button', { name: /only up to INR 2,500/ }))
    await user.click(screen.getByRole('tab', { name: 'Report' }))

    await user.click(screen.getByRole('button', { name: /refunds up to INR 5,000 per request/ }))

    const first = screen.getByRole('region', { name: 'Section 3.1-3.5', hidden: true })
    expect(first.querySelector('mark')).toHaveTextContent(/^refunds up to INR 5,000 per request$/)
    const second = screen.getByRole('region', { name: 'Section 5.1-5.4', hidden: true })
    expect(second.querySelector('mark')).toBeNull()
    expect(second).not.toHaveAttribute('aria-current')
  })

  it('copies the suggested question and says so', async () => {
    const { user } = await open()
    // user-event installs its own clipboard, so the spy goes on that one.
    const writeText = vi.spyOn(navigator.clipboard, 'writeText')
    await expand(user, 'No owner for refund disputes')

    await user.click(screen.getByRole('button', { name: 'Copy question' }))

    expect(writeText).toHaveBeenCalledWith('Who owns a refund dispute?')
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
    expect(
      await screen.findByRole('button', { name: 'Copy question' }, { timeout: 3000 }),
    ).toBeInTheDocument()
  })

  it('offers to select the text when copying fails', async () => {
    const { user } = await open()
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'))
    await expand(user, 'No owner for refund disputes')

    await user.click(screen.getByRole('button', { name: 'Copy question' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not copy. Select the text instead.',
    )
  })

  it('saves a review status and shows the one the server stored', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const { user, fake } = await open({
      [patchOf('f-owner')]: async () => {
        await gate
        return { body: { finding: { ...OWNER, review_status: 'confirmed' } } }
      },
    })
    await expand(user, 'No owner for refund disputes')
    const status = screen.getByRole('group', { name: 'Review status' })

    await user.click(within(status).getByRole('button', { name: 'Confirmed' }))

    expect(within(status).getByRole('button', { name: 'Open' })).toBeDisabled()
    expect(fake.to('/findings/f-owner')[0]?.body).toEqual({ review_status: 'confirmed' })
    release()
    await waitFor(() =>
      expect(within(status).getByRole('button', { name: 'Confirmed' })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    )
    expect(within(status).getByRole('button', { name: 'Open' })).toBeEnabled()
    expect(screen.getByRole('button', { name: /No owner for refund disputes/ })).toHaveTextContent(
      'Confirmed',
    )
  })

  it('keeps the old status and says so when saving fails', async () => {
    const { user } = await open({
      [patchOf('f-owner')]: () => problem(500, 'internal_error', 'Server wording.'),
    })
    await expand(user, 'No owner for refund disputes')
    const status = screen.getByRole('group', { name: 'Review status' })

    await user.click(within(status).getByRole('button', { name: 'Dismissed' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The status could not be saved. Try again.')
    expect(alert).toHaveTextContent('Request id: req-12345678')
    expect(alert).not.toHaveTextContent('Server wording')
    expect(within(status).getByRole('button', { name: 'Open' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('filters by severity and by kind, and clears the filters', async () => {
    const { user } = await open()
    await screen.findByRole('list', { name: 'Findings' })
    const severity = screen.getByRole('group', { name: 'Severity' })
    const kind = screen.getByRole('group', { name: 'Kind' })

    await user.click(within(severity).getByRole('button', { name: 'High' }))
    expect(within(findingsList()).getAllByRole('listitem')).toHaveLength(1)
    expect(findingsList()).toHaveTextContent('Refund limit differs')

    await user.click(within(severity).getByRole('button', { name: 'All' }))
    await user.click(within(kind).getByRole('button', { name: 'Unclear' }))
    expect(findingsList()).toHaveTextContent('L2 is not defined')
    expect(within(findingsList()).getAllByRole('listitem')).toHaveLength(1)

    await user.click(within(severity).getByRole('button', { name: 'High' }))
    expect(screen.getByText('No findings match these filters.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(within(findingsList()).getAllByRole('listitem')).toHaveLength(3)
  })

  it('shows text from the model as text, never as HTML', async () => {
    const hostile = finding({
      id: 'f-hostile',
      title: '<b>bold</b> title',
      citations: [{ chunk_id: 'chunk-a', section_label: null, quote: '<script>x</script>' }],
    })
    const { user } = await open({ [LATEST]: () => report({ findings: [hostile] }) })

    await expand(user, '<b>bold</b> title')

    expect(screen.getByText('<script>x</script>')).toBeInTheDocument()
    expect(document.body.querySelector('b')).toBeNull()
    expect(document.body.querySelector('script')).toBeNull()
  })
})

describe('starting a report', () => {
  it('starts one, shows that it is running, and shows it when it is done', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let started = false
    let polls = 0
    const { user, fake } = await open({
      [LATEST]: () => {
        if (!started) {
          return problem(404, 'analysis_not_found', 'x')
        }
        polls += 1
        return polls < 2
          ? report({ status: 'running', findings: [], findings_count: 0, completed_at: null })
          : report()
      },
      [START]: () => {
        started = true
        return {
          status: 202,
          body: { analysis: analysis({ status: 'queued', findings: [], completed_at: null }) },
        }
      },
    })

    expect(await screen.findByText(/No report yet/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Generate report' }))

    expect(await screen.findByText(/Generating the report/)).toBeInTheDocument()
    expect(fake.to('/analyses')).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(2000)

    expect(await screen.findByRole('list', { name: 'Findings' })).toBeInTheDocument()
    expect(screen.queryByText(/Generating the report/)).not.toBeInTheDocument()
  })

  it('shows the running report when one was already started elsewhere', async () => {
    let started = false
    const { user } = await open({
      [LATEST]: () =>
        started
          ? report({ status: 'running', findings: [], completed_at: null })
          : problem(404, 'analysis_not_found', 'x'),
      [START]: () => {
        started = true
        return problem(409, 'analysis_already_running', 'x')
      },
    })

    await user.click(await screen.findByRole('button', { name: 'Generate report' }))

    expect(await screen.findByText(/Generating the report/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('asks before running again over a finished report', async () => {
    const { user, fake } = await open({
      [START]: () => ({
        status: 202,
        body: { analysis: analysis({ status: 'queued', findings: [], completed_at: null }) },
      }),
    })
    await screen.findByRole('list', { name: 'Findings' })

    await user.click(screen.getByRole('button', { name: 'Run again' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Run the report again?' })
    expect(dialog).toHaveTextContent('including the review statuses you set')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(fake.to('/analyses')).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Run again' }))
    await user.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Run again' }),
    )

    await waitFor(() => expect(fake.to('/analyses')).toHaveLength(1))
  })

  it('shows why a report failed and tries again without asking', async () => {
    const { user, fake } = await open({
      [LATEST]: () =>
        report({
          status: 'failed',
          findings: [],
          error_message: 'The analysis took too long. Try again.',
        }),
      [START]: () => ({
        status: 202,
        body: { analysis: analysis({ status: 'queued', findings: [], completed_at: null }) },
      }),
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The analysis took too long. Try again.')
    expect(screen.queryByRole('button', { name: 'Run again' })).not.toBeInTheDocument()
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await waitFor(() => expect(fake.to('/analyses')).toHaveLength(1))
  })

  it('explains a start that is refused and offers to try again', async () => {
    const { user } = await open({
      [LATEST]: () => problem(404, 'analysis_not_found', 'x'),
      [START]: () => ({ ...problem(429, 'rate_limited', 'x'), headers: { 'Retry-After': '1800' } }),
    })

    await user.click(await screen.findByRole('button', { name: 'Generate report' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('You have started too many reports. Try again in 30 minutes.')
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('cannot start before the document is ready, and asks for no report', async () => {
    const { fake } = await open({
      [DOCUMENT]: () => ({
        body: { document: documentDetails({ id: ID, title: 'Refund SOP', status: 'processing' }) },
      }),
    })

    expect(
      screen.getByText('A report can be generated when the document is ready.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate report' })).toBeDisabled()
    expect(fake.to('/analyses/latest')).toHaveLength(0)
  })
})

describe('empty and failed loads', () => {
  it('says so when the report found no gaps', async () => {
    await open({ [LATEST]: () => report({ findings: [], findings_count: 0 }) })

    expect(
      await screen.findByText('The report found no gaps in this document.'),
    ).toBeInTheDocument()
  })

  it('explains a report emptied because no quote could be verified', async () => {
    await open({
      [LATEST]: () => report({ findings: [], findings_count: 0, dropped_findings_count: 2 }),
    })

    const note = await screen.findByRole('note')
    expect(note).toHaveTextContent(
      'No findings can be shown. The report suggested 2, but their quotes could not be found in the document, so they were removed.',
    )
    expect(screen.queryByText(/found no gaps/)).not.toBeInTheDocument()
  })

  it('says how many more findings were removed', async () => {
    await open({ [LATEST]: () => report({ dropped_findings_count: 1 }) })

    expect(
      await screen.findByText(
        '1 more finding was removed because its quote could not be found in the document.',
      ),
    ).toBeInTheDocument()
  })

  it('shows a skeleton while the report loads', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    await open({
      [LATEST]: async () => {
        await gate
        return report()
      },
    })

    expect(screen.getByRole('status', { name: 'Loading the report' })).toBeInTheDocument()
    release()
    expect(await screen.findByRole('list', { name: 'Findings' })).toBeInTheDocument()
  })

  it('shows a load error with the request id and tries again', async () => {
    let calls = 0
    const { user } = await open({
      [LATEST]: () => {
        calls += 1
        return calls === 1 ? problem(500, 'internal_error', 'x') : report()
      },
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The report could not be loaded. Try again.')
    expect(alert).toHaveTextContent('Request id: req-12345678')
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('list', { name: 'Findings' })).toBeInTheDocument()
  })
})
