import { MoreHorizontal } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatDateTime } from '@/lib/format'

import { DeleteDocumentDialog } from './DeleteDocumentDialog'
import type { DocumentSummary } from './schemas'
import { StatusBadge } from './StatusBadge'

function pagesLabel(count: number | null): string {
  if (count === null) {
    return 'Text file'
  }
  return count === 1 ? '1 page' : `${count} pages`
}

function DocumentRow({ document }: { document: DocumentSummary }) {
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const actionsLabel = `Actions for ${document.title}`

  return (
    <TableRow>
      <TableCell className="max-w-0 min-w-40 whitespace-normal">
        <Link
          to={`/documents/${document.id}`}
          className="font-medium break-words text-primary hover:underline"
        >
          {document.title}
        </Link>
        <p className="mt-1 text-xs text-muted-foreground sm:hidden">
          {pagesLabel(document.page_count)} · {formatDateTime(document.created_at)}
        </p>
      </TableCell>
      <TableCell>
        <StatusBadge status={document.status} />
      </TableCell>
      <TableCell className="hidden sm:table-cell">{pagesLabel(document.page_count)}</TableCell>
      <TableCell className="hidden sm:table-cell">{formatDateTime(document.created_at)}</TableCell>
      <TableCell className="w-12 text-right">
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={actionsLabel}>
                  <MoreHorizontal aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent>Actions</TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="end">
            <DropdownMenuItem asChild>
              <Link to={`/documents/${document.id}`}>Open</Link>
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmingDelete(true)}>
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <DeleteDocumentDialog
          documentId={document.id}
          title={document.title}
          open={confirmingDelete}
          onOpenChange={setConfirmingDelete}
        />
      </TableCell>
    </TableRow>
  )
}

export function DocumentsTable({ documents }: { documents: DocumentSummary[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Title</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="hidden sm:table-cell">Pages</TableHead>
          <TableHead className="hidden sm:table-cell">Uploaded</TableHead>
          <TableHead className="w-12">
            <span className="sr-only">Actions</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.map((document) => (
          <DocumentRow key={document.id} document={document} />
        ))}
      </TableBody>
    </Table>
  )
}
