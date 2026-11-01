import { Loader2 } from 'lucide-react'

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { ApiError } from '@/lib/api'

import { useDeleteDocument } from './hooks'

interface Props {
  documentId: string
  title: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Asks first, and names the document, because deleting cannot be undone. */
export function DeleteDocumentDialog({ documentId, title, open, onOpenChange }: Props) {
  const deletion = useDeleteDocument()

  function handleOpenChange(next: boolean) {
    if (!next) {
      deletion.reset()
    }
    onOpenChange(next)
  }

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{title}”?</AlertDialogTitle>
          <AlertDialogDescription>
            The document text is removed and you can no longer open it. You can upload the file
            again afterwards.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {deletion.isError && (
          <p role="alert" className="text-destructive">
            The document could not be deleted. Try again.
            {deletion.error instanceof ApiError && deletion.error.requestId !== null && (
              <span className="mt-1 block text-xs text-muted-foreground">
                Request id: {deletion.error.requestId}
              </span>
            )}
          </p>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deletion.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={deletion.isPending}
            onClick={(event) => {
              // Keep the dialog open until the server has answered.
              event.preventDefault()
              deletion.mutate(documentId, { onSuccess: () => onOpenChange(false) })
            }}
          >
            {deletion.isPending && <Loader2 aria-hidden="true" className="animate-spin" />}
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
