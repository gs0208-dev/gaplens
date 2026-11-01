/** A date and time in the user's locale, as docs/design-system.md asks. */
export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  )
}

/** "less than a minute", "5 minutes", "2 hours": how long to wait, in words. */
export function formatWait(seconds: number | null): string {
  if (seconds === null || seconds < 60) {
    return 'a minute'
  }
  const minutes = Math.ceil(seconds / 60)
  if (minutes < 60) {
    return minutes === 1 ? '1 minute' : `${minutes} minutes`
  }
  const hours = Math.ceil(minutes / 60)
  return hours === 1 ? '1 hour' : `${hours} hours`
}
