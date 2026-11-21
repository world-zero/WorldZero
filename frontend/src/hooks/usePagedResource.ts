import { useCallback, useEffect, useState, type DependencyList } from 'react'
import { useResource } from './useResource'
import type { KeyedResourceCache } from './cachedResource'
import { CACHE_EPOCH } from '../utils/cacheEpoch'
import type { CurrentUser } from '../api/auth'

// Test-only exports are deliberate (#2693): no DOM in tests, so these pure seams
// are the only way to assert the load-more and cache-key contracts.

export const DEFAULT_PAGE_SIZE = 50

/** Load more iff the last page came back full — no total count needed. */
export function pageHasMore(
  loaded: number | null | undefined,
  offset: number,
  pageSize: number,
): boolean {
  return loaded === offset + pageSize
}

/**
 * Opt a paged list into the Class B cache (#2432, ADR-0072). The cache is the
 * caller's (module scope, one per list); the key is built here from deps + viewer.
 */
export interface PagedCache<T> {
  /** `createKeyedResourceCache<T[]>(AMBIENT_TTL_MS)` at the caller's module scope. */
  cache: KeyedResourceCache<T[]>
  /** {@link viewerCacheKey}. Rows are viewer-relative (`can_sign_up` etc.). */
  viewer: string
}

/**
 * Account + character (eligibility is per life); 'anon' is a real cacheable
 * board. In-memory only, never sent anywhere.
 */
export function viewerCacheKey(user: CurrentUser | null): string {
  if (user === null) return 'anon'
  return `${user.account_id}:${user.character?.id ?? '-'}`
}

/** `JSON.stringify`, not a separator: one axis is free-text search. */
export function pageCacheKey(viewer: string, deps: DependencyList): string {
  return JSON.stringify([viewer, ...deps])
}

/**
 * One page read; caches the FIRST page only (repeat views are first-page events).
 * A request never asks for more than `pageSize` rows, so it stays under any
 * route's `limit` ceiling however deep the list goes.
 */
export function loadPage<T>(
  fetchPage: (offset: number, limit: number) => Promise<T[]>,
  offset: number,
  pageSize: number,
  deps: DependencyList,
  cached: PagedCache<T> | undefined,
): Promise<T[]> {
  if (cached === undefined || offset !== 0) return fetchPage(offset, pageSize)
  return cached.cache.read(pageCacheKey(cached.viewer, deps), () =>
    fetchPage(0, pageSize),
  )
}

interface PagedResource<T> {
  data: T[] | null
  loading: boolean
  error: Error | null
  hasMore: boolean
  /** Fetch the next page and append it. */
  loadMore: () => void
  /** Call on filter/sort change so a grown window isn't stranded. */
  resetWindow: () => void
}

/**
 * Offset pagination over {@link useResource} (#644): "load more" fetches the next
 * `pageSize` rows and appends them. `deps` is the caller's filter key; wrap
 * filter setters with `resetWindow()`. `cached` opts the first page into Class B
 * (see {@link loadPage}). Offset paging can repeat or skip a row if the list
 * shifts between loads; a refresh resets it.
 */
export function usePagedResource<T>(
  fetchPage: (offset: number, limit: number) => Promise<T[]>,
  deps: DependencyList,
  pageSize: number = DEFAULT_PAGE_SIZE,
  cached?: PagedCache<T>,
): PagedResource<T> {
  const [pageState, setWindow] = useState<{ prior: T[]; offset: number }>({
    prior: [],
    offset: 0,
  })
  const { prior, offset } = pageState

  const { data, loading, error, refetch } = useResource(
    async () => [
      ...prior,
      ...(await loadPage(fetchPage, offset, pageSize, deps, cached)),
    ],
    [...deps, offset],
  )

  // Re-read on era rollover (epoch outranks TTL, ADR-0072); held pages are stale.
  const isCached = cached !== undefined
  const restart = useCallback(() => {
    setWindow({ prior: [], offset: 0 })
    refetch()
  }, [refetch])
  useEffect(
    () => (isCached ? CACHE_EPOCH.onDrop(restart) : undefined),
    [isCached, restart],
  )

  return {
    data,
    loading,
    error,
    hasMore: pageHasMore(data?.length, offset, pageSize),
    loadMore: () => {
      if (data !== null) setWindow({ prior: data, offset: data.length })
    },
    resetWindow: () => setWindow({ prior: [], offset: 0 }),
  }
}
