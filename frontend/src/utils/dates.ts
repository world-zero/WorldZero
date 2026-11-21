import { formatCompactTime } from './commentTime'

export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function formatDate(iso: string, options: Intl.DateTimeFormatOptions = { dateStyle: 'medium' }): string {
  return new Date(iso).toLocaleDateString(undefined, options)
}

/** Clock time plus zone name; the weekday leads when not today, so it never reads as earlier. */
export function formatClockTime(
  iso: string,
  { timeZone, now = new Date() }: { timeZone?: string; now?: Date } = {},
): string {
  const at = new Date(iso)
  const day = (d: Date) =>
    new Intl.DateTimeFormat(undefined, { timeZone, dateStyle: 'short' }).format(d)
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    ...(day(at) === day(now) ? {} : { weekday: 'short' }),
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(at)
}

/** The feed's compact age; the words live in the catalog (`formatCompactTime`). */
export const relativeTime = formatCompactTime
