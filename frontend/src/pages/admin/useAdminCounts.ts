import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  getFlaggedComments,
  getFlaggedPraxes,
  getMessages,
  getOverview,
  getPendingTasks,
} from '../../api/admin'
import { useCan, type Need } from '../../auth/permissions'

/** `null` = not loaded, or that endpoint failed: the rail then shows no number rather than a wrong one. */
export interface AdminCounts {
  reports: number | null
  messages: number | null
  proposals: number | null
  praxis: number | null
  tasks: number | null
  people: number | null
}

/** The MOD button's queues; a queue the caller holds no permission for stays `null`, so it is never fetched or summed. */
export const MOD_QUEUES = ['reports', 'messages', 'proposals'] as const satisfies readonly (keyof AdminCounts & Need)[]

export const modTotal = (c: AdminCounts): number => MOD_QUEUES.reduce((sum, key) => sum + (c[key] ?? 0), 0)

const NONE: AdminCounts = { reports: null, messages: null, proposals: null, praxis: null, tasks: null, people: null }

const ok = <T,>(r: PromiseSettledResult<T>): T | null => (r.status === 'fulfilled' ? r.value : null)

/**
 * What needs a moderator, for the admin rail (and #3666's MOD badge). Class C
 * (ADR-0072): these are obligations, so never cached; `refreshKey` re-reads
 * after the moderator has moved (the rail passes the pathname); `reload`
 * re-reads on demand, for a decision that doesn't change the route.
 */
export function useAdminCounts(refreshKey = ''): AdminCounts & { reload: () => void } {
  const [counts, setCounts] = useState<AdminCounts>(NONE)
  const [bump, setBump] = useState(0)
  const can = useCan()
  const held = MOD_QUEUES.map(can)
  const [reports, messages, proposals] = held

  useEffect(() => {
    let cancelled = false
    const skip = Promise.reject<never>()
    skip.catch(() => {})
    void Promise.allSettled([
      reports ? getFlaggedPraxes() : skip,
      reports ? getFlaggedComments() : skip,
      messages ? getMessages(false) : skip,
      proposals ? getPendingTasks() : skip,
      getOverview(),
    ]).then(([praxes, comments, messages, proposals, overview]) => {
      if (cancelled) return
      const p = ok(praxes)
      const c = ok(comments)
      const o = ok(overview)
      setCounts({
        reports: p && c ? p.length + c.length : null,
        messages: ok(messages)?.length ?? null,
        proposals: ok(proposals)?.length ?? null,
        praxis: o?.praxis ?? null,
        tasks: o?.active_tasks ?? null,
        people: o?.characters ?? null,
      })
    })
    return () => {
      cancelled = true
    }
  }, [refreshKey, bump, held.join()])

  return { ...counts, reload: () => setBump((n) => n + 1) }
}

/** The console layout's `reload`, for a page's action handlers; a no-op where the page is mounted outside the console. */
export function useReloadCounts(): () => void {
  return useOutletContext<{ reloadCounts: () => void } | undefined>()?.reloadCounts ?? (() => {})
}
