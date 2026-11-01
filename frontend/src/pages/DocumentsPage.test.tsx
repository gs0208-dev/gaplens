import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DOCUMENT_LIST, problem, stubApi, type FakeResponse } from '@/test/fetch'
import { documentSummary, SIGNED_IN } from '@/test/fixtures'
import { renderApp, resetClientState } from '@/test/render'

beforeEach(resetClientState)
afterEach(() => vi.useRealTimers())

type Routes = Parameters<typeof stubApi>[0]

function list(...items: Record<string, unknown>[]): FakeResponse {
  return { body: { items, next_cursor: null } }
}

async function openDocuments(routes: Routes) {
  const fake = stubApi({ ...SIGNED_IN, ...routes })
  const page = renderApp('/documents')
  await screen.findByRole('heading', { name: 'Documents' })
  return { fake, ...page }
}

describe('the documents list', () => {
  it('shows a skeleton while the list loads, then the rows', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    await openDocuments({
      [DOCUMENT_LIST]: async () => {
        await gate
        return list(documentSummary({ title: 'Refund SOP' }))
      },
    })

    expect(await screen.findByRole('status', { name: 'Loading documents' })).toBeInTheDocument()
    release()

    expect(await screen.findByRole('link', { name: 'Refund SOP' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Loading documents' })).not.toBeInTheDocument()
  })

  it('shows title, status in words, pages and date for each document', async () => {
    const ready = documentSummary({ title: 'Refund SOP', status: 'ready', page_count: 3 })
    const text = documentSummary({ title: 'Notes', status: 'processing', page_count: null })
    const failed = documentSummary({ title: 'Broken', status: 'failed', page_count: 1 })
    const queued = documentSummary({ title: 'Waiting', status: 'uploaded', page_count: 12 })
    await openDocuments({ [DOCUMENT_LIST]: () => list(ready, text, failed, queued) })

    const row = (await screen.findByRole('link', { name: 'Refund SOP' })).closest('tr')
    expect(row).not.toBeNull()
    const cells = within(row as HTMLElement)
    expect(cells.getByText('Ready')).toBeInTheDocument()
    expect(cells.getByText('3 pages')).toBeInTheDocument()
    expect(cells.getAllByText(/2026/).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'Refund SOP' })).toHaveAttribute(
      'href',
      `/documents/${ready.id}`,
    )
    expect(screen.getByText('Processing')).toBeInTheDocument()
    expect(screen.getByText('Text file')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('Queued')).toBeInTheDocument()
    expect(screen.getByText('12 pages')).toBeInTheDocument()
  })

  it('says what to do when there are no documents', async () => {
    await openDocuments({ [DOCUMENT_LIST]: () => list() })

    expect(await screen.findByText(/You have no documents yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload document' })).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows what went wrong with the request id, and tries again on request', async () => {
    let calls = 0
    const { user } = await openDocuments({
      [DOCUMENT_LIST]: () => {
        calls += 1
        return calls === 1
          ? problem(500, 'internal_error', 'Something went wrong on our side.')
          : list(documentSummary({ title: 'Refund SOP' }))
      },
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The documents could not be loaded. Try again.')
    expect(alert).toHaveTextContent('Request id: req-12345678')
    expect(alert).not.toHaveTextContent('Something went wrong on our side')

    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('link', { name: 'Refund SOP' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('loads the next page with the cursor and appends it', async () => {
    const first = documentSummary({ title: 'First' })
    const second = documentSummary({ title: 'Second' })
    const { user, fake } = await openDocuments({
      [DOCUMENT_LIST]: () => ({ body: { items: [first], next_cursor: 'cursor-1' } }),
      'GET /api/v1/documents?limit=20&cursor=cursor-1': () => list(second),
    })

    await user.click(await screen.findByRole('button', { name: 'Load more' }))

    expect(await screen.findByRole('link', { name: 'Second' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'First' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
    expect(fake.to('limit=20&cursor=cursor-1')).toHaveLength(1)
  })
})

describe('status polling', () => {
  it('asks again every 2 seconds while a document is processing, and stops once it is ready', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const id = 'doc-polled'
    let calls = 0
    const { fake } = await openDocuments({
      [DOCUMENT_LIST]: () => {
        calls += 1
        const status = calls < 3 ? 'processing' : 'ready'
        return list(documentSummary({ id, title: 'Polled', status }))
      },
    })
    expect(await screen.findByText('Processing')).toBeInTheDocument()

    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(2000)

    expect(await screen.findByText('Ready')).toBeInTheDocument()
    const requestsWhenReady = fake.to('/api/v1/documents?limit=20').length
    expect(requestsWhenReady).toBe(3)

    await vi.advanceTimersByTimeAsync(10_000)

    expect(fake.to('/api/v1/documents?limit=20')).toHaveLength(requestsWhenReady)
  })

  it('does not poll a list of finished documents', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { fake } = await openDocuments({
      [DOCUMENT_LIST]: () =>
        list(documentSummary({ status: 'ready' }), documentSummary({ status: 'failed' })),
    })
    await screen.findByText('Ready')

    await vi.advanceTimersByTimeAsync(10_000)

    expect(fake.to('/api/v1/documents?limit=20')).toHaveLength(1)
  })
})

describe('uploading', () => {
  const POST = 'POST /api/v1/documents'
  const pdf = () => new File(['%PDF-1.4 text'], 'sop.pdf', { type: 'application/pdf' })

  async function openDialog(routes: Routes = {}) {
    const page = await openDocuments({ [DOCUMENT_LIST]: () => list(), ...routes })
    await page.user.click(await screen.findByRole('button', { name: 'Upload document' }))
    await screen.findByRole('dialog', { name: 'Upload a document' })
    return page
  }

  it('states what is accepted, the size limit and what happens to the text', async () => {
    await openDialog()

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('PDF, text or Markdown file up to 5 MB')
    expect(dialog).toHaveTextContent('Scanned PDFs are not supported')
    expect(dialog).toHaveTextContent('sent to Anthropic')
  })

  it('sends the file and the title as a multipart upload, closes, and shows the new row', async () => {
    let uploaded = false
    const created = documentSummary({ title: 'Quarterly SOP', status: 'uploaded' })
    const { user, fake } = await openDialog({
      [DOCUMENT_LIST]: () => list(...(uploaded ? [created] : [])),
      [POST]: () => {
        uploaded = true
        return {
          status: 202,
          body: {
            document: {
              ...created,
              filename: 'sop.pdf',
              mime_type: 'application/pdf',
              size_bytes: 13,
              error_message: null,
            },
          },
        }
      },
    })

    await user.upload(screen.getByLabelText('File'), pdf())
    await user.type(screen.getByLabelText('Title (optional)'), 'Quarterly SOP')
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('link', { name: 'Quarterly SOP' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const [request] = fake.to('/api/v1/documents').filter((r) => r.method === 'POST')
    expect(request?.form?.file).toBeInstanceOf(File)
    expect((request?.form?.file as File).name).toBe('sop.pdf')
    expect(request?.form?.title).toBe('Quarterly SOP')
    expect(request?.headers.get('Content-Type')).toBeNull()
    expect(request?.headers.get('Authorization')).toMatch(/^Bearer /)
  })

  it('leaves the title out when none is typed', async () => {
    const { user, fake } = await openDialog({
      [POST]: () => ({
        status: 202,
        body: {
          document: {
            ...documentSummary(),
            filename: 'a',
            mime_type: 'text/plain',
            size_bytes: 1,
            error_message: null,
          },
        },
      }),
    })

    await user.upload(screen.getByLabelText('File'), pdf())
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    await waitFor(() =>
      expect(fake.to('/api/v1/documents').some((r) => r.method === 'POST')).toBe(true),
    )
    const [request] = fake.to('/api/v1/documents').filter((r) => r.method === 'POST')
    expect(request?.form).not.toHaveProperty('title')
  })

  it('shows Uploading and disables the button while the request runs', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const { user } = await openDialog({
      [POST]: async () => {
        await gate
        return {
          status: 202,
          body: {
            document: {
              ...documentSummary(),
              filename: 'a',
              mime_type: 'text/plain',
              size_bytes: 1,
              error_message: null,
            },
          },
        }
      },
    })

    await user.upload(screen.getByLabelText('File'), pdf())
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('button', { name: 'Uploading' })).toBeDisabled()
    release()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('refuses a file over 5 MB without sending it', async () => {
    const { user, fake } = await openDialog()
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'big.pdf', {
      type: 'application/pdf',
    })

    await user.upload(screen.getByLabelText('File'), big)
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('This file is larger than 5 MB.')
    expect(fake.requests.some((r) => r.method === 'POST' && r.url.endsWith('/documents'))).toBe(
      false,
    )
  })

  it('asks for a file when none was chosen', async () => {
    const { user, fake } = await openDialog()

    await user.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a file to upload.')
    expect(fake.requests.some((r) => r.method === 'POST' && r.url.endsWith('/documents'))).toBe(
      false,
    )
  })

  it('refuses a title over 200 characters without sending anything', async () => {
    const { user, fake } = await openDialog()

    await user.upload(screen.getByLabelText('File'), pdf())
    await user.click(screen.getByLabelText('Title (optional)'))
    await user.paste('t'.repeat(201))
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByText('The title can be at most 200 characters.')).toBeInTheDocument()
    expect(fake.requests.some((r) => r.method === 'POST' && r.url.endsWith('/documents'))).toBe(
      false,
    )
  })

  it.each([
    ['unsupported_file_type', 415, 'Upload a PDF, a plain text file or a Markdown file.'],
    [
      'encrypted_pdf',
      422,
      'This PDF is password protected. Remove the protection and upload it again.',
    ],
    [
      'no_extractable_text',
      422,
      'No text could be read from this file. Scanned documents are not supported.',
    ],
    ['too_many_pages', 422, 'This document has more than 100 pages.'],
    [
      'duplicate_document',
      409,
      'You have already uploaded this file. Delete the earlier one to upload it again.',
    ],
    ['file_too_large', 413, 'This file is larger than 5 MB.'],
  ])('shows the plain message for %s and keeps the dialog open', async (code, status, message) => {
    const { user } = await openDialog({
      [POST]: () => problem(status, code, 'Server wording that is not shown.'),
    })

    await user.upload(screen.getByLabelText('File'), pdf())
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(message)
    expect(alert).toHaveTextContent('Request id: req-12345678')
    expect(alert).not.toHaveTextContent('Server wording')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload' })).toBeEnabled()
  })

  it('says how long to wait when the upload limit is reached', async () => {
    const { user } = await openDialog({
      [POST]: () => ({
        ...problem(429, 'rate_limited', 'Too many'),
        headers: { 'Retry-After': '300' },
      }),
    })

    await user.upload(screen.getByLabelText('File'), pdf())
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You have uploaded too many documents. Try again in 5 minutes.',
    )
  })

  it('forgets the chosen file and any error when it is cancelled and opened again', async () => {
    const { user } = await openDialog()
    await user.upload(screen.getByLabelText('File'), pdf())
    expect(screen.getByText('sop.pdf')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Upload document' }))

    await screen.findByRole('dialog', { name: 'Upload a document' })
    expect(screen.queryByText('sop.pdf')).not.toBeInTheDocument()
  })
})

describe('deleting', () => {
  async function openMenu(routes: Routes) {
    const doc = documentSummary({ title: 'Refund SOP' })
    const page = await openDocuments({ [DOCUMENT_LIST]: () => list(doc), ...routes })
    await page.user.click(await screen.findByRole('button', { name: 'Actions for Refund SOP' }))
    return { ...page, doc }
  }

  it('asks first, naming the document, and does nothing on cancel', async () => {
    const { user, fake } = await openMenu({})

    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }))

    expect(
      await screen.findByRole('alertdialog', { name: 'Delete “Refund SOP”?' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(fake.requests.some((r) => r.method === 'DELETE')).toBe(false)
    expect(screen.getByRole('link', { name: 'Refund SOP' })).toBeInTheDocument()
  })

  it('deletes after confirming and the row disappears', async () => {
    let deleted = false
    const { user, fake, doc } = await openMenu({
      [DOCUMENT_LIST]: () =>
        list(...(deleted ? [] : [documentSummary({ id: 'doc-x', title: 'Refund SOP' })])),
      'DELETE /api/v1/documents/doc-x': () => {
        deleted = true
        return { status: 204 }
      },
    })
    expect(doc.title).toBe('Refund SOP')

    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    await user.click(await screen.findByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(screen.queryByRole('link', { name: 'Refund SOP' })).not.toBeInTheDocument(),
    )
    expect(fake.requests.filter((r) => r.method === 'DELETE')).toHaveLength(1)
    expect(await screen.findByText(/You have no documents yet/)).toBeInTheDocument()
  })

  it('keeps the dialog open and says so when deleting fails', async () => {
    const { user } = await openMenu({
      'DELETE /api/v1/documents/doc-fail': () => problem(500, 'internal_error', 'No'),
      [DOCUMENT_LIST]: () => list(documentSummary({ id: 'doc-fail', title: 'Refund SOP' })),
    })

    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    await user.click(await screen.findByRole('button', { name: 'Delete' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The document could not be deleted. Try again.',
    )
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })
})
