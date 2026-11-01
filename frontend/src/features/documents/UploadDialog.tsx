import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2, Upload } from 'lucide-react'
import { useId, useRef, useState, type DragEvent } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

import { MAX_UPLOAD_BYTES, uploadError, type ShownError } from './errors'
import { useUploadDocument } from './hooks'

const ACCEPTED = '.pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown'

const formSchema = z.object({
  title: z.string().max(200, 'The title can be at most 200 characters.'),
})
type FormValues = z.infer<typeof formSchema>

export function UploadDialog() {
  const [open, setOpen] = useState(false)
  const upload = useUploadDocument()
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [serverError, setServerError] = useState<ShownError | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const fileHelpId = useId()
  const fileErrorId = useId()
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { title: '' },
  })

  function reset() {
    setFile(null)
    setFileError(null)
    setServerError(null)
    setDragging(false)
    upload.reset()
    form.reset()
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      reset()
    }
    setOpen(next)
  }

  function choose(candidate: File | undefined) {
    setServerError(null)
    if (candidate === undefined) {
      return
    }
    if (candidate.size > MAX_UPLOAD_BYTES) {
      // Refused here, without sending 5 MB just to be told no.
      setFile(null)
      setFileError('This file is larger than 5 MB.')
      return
    }
    setFile(candidate)
    setFileError(null)
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    choose(event.dataTransfer.files[0])
  }

  function submit(values: FormValues) {
    if (file === null) {
      // Keep an earlier reason, such as "larger than 5 MB", instead of hiding it.
      setFileError((current) => current ?? 'Choose a file to upload.')
      return
    }
    setServerError(null)
    upload.mutate(
      { file, title: values.title },
      {
        onSuccess: () => handleOpenChange(false),
        onError: (error) => setServerError(uploadError(error)),
      },
    )
  }

  const shownFileError = fileError ?? serverError?.message ?? null

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <Upload aria-hidden="true" />
          Upload document
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload a document</DialogTitle>
          <DialogDescription>Upload a PDF, text or Markdown file up to 5 MB.</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(submit)} noValidate className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="document-file" className="text-sm leading-none font-medium">
                File
              </label>
              <div
                onDragOver={(event) => {
                  event.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                className={cn(
                  'flex flex-col items-start gap-2 rounded-md border border-dashed border-input bg-surface-muted p-4',
                  dragging && 'border-primary bg-accent',
                )}
              >
                <p className="text-muted-foreground">Drop a file here, or choose one.</p>
                <input
                  ref={fileInput}
                  id="document-file"
                  type="file"
                  accept={ACCEPTED}
                  className="sr-only"
                  aria-describedby={
                    shownFileError === null ? fileHelpId : `${fileHelpId} ${fileErrorId}`
                  }
                  aria-invalid={shownFileError !== null}
                  onChange={(event) => choose(event.target.files?.[0])}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInput.current?.click()}
                >
                  Choose file
                </Button>
                {file !== null && (
                  <p className="font-mono text-xs break-all" aria-live="polite">
                    {file.name}
                  </p>
                )}
              </div>
              <p id={fileHelpId} className="text-xs text-muted-foreground">
                Accepted: PDF (up to 100 pages), plain text and Markdown. Scanned PDFs are not
                supported.
              </p>
              {shownFileError !== null && (
                <p id={fileErrorId} role="alert" className="text-sm text-destructive">
                  {shownFileError}
                  {serverError?.requestId != null && fileError === null && (
                    <span className="mt-1 block text-xs text-muted-foreground">
                      Request id: {serverError.requestId}
                    </span>
                  )}
                </p>
              )}
            </div>
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Title (optional)</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <p className="text-xs text-muted-foreground">
              The document text is stored in your account. When you ask a question, the matching
              excerpts are sent to Anthropic to write the answer.
            </p>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={upload.isPending}>
                {upload.isPending && <Loader2 aria-hidden="true" className="animate-spin" />}
                {upload.isPending ? 'Uploading' : 'Upload'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
