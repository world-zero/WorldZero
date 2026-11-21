/** #645 — `usePagedResource`'s offset-paging math. */
import { describe, it, expect } from 'vitest'
import { pageHasMore, loadPage, DEFAULT_PAGE_SIZE } from '../usePagedResource'

describe('pageHasMore — load more iff the last page came back full', () => {
  it('is true when the last page fills exactly', () => {
    expect(pageHasMore(50, 0, 50)).toBe(true)
    expect(pageHasMore(100, 50, 50)).toBe(true)
  })

  it('is false when a short page signals the end', () => {
    expect(pageHasMore(37, 0, 50)).toBe(false)
    expect(pageHasMore(128, 100, 50)).toBe(false)
  })

  it('is false before the first page settles (null / undefined length)', () => {
    expect(pageHasMore(null, 0, 50)).toBe(false)
    expect(pageHasMore(undefined, 0, 50)).toBe(false)
  })
})

describe('loadPage — a request never exceeds the page size', () => {
  it('walks 600 rows with limit fixed at the page size, past any route ceiling', async () => {
    const calls: Array<[number, number]> = []
    const fetchPage = (offset: number, limit: number) => {
      calls.push([offset, limit])
      return Promise.resolve(Array.from({ length: Math.min(limit, 600 - offset) }, (_, i) => offset + i))
    }
    let loaded = 0
    let offset = 0
    do {
      offset = loaded
      loaded += (await loadPage(fetchPage, offset, DEFAULT_PAGE_SIZE, [], undefined)).length
    } while (pageHasMore(loaded, offset, DEFAULT_PAGE_SIZE))
    expect(loaded).toBe(600)
    expect(calls.length).toBe(13)
    expect(Math.max(...calls.map(([, limit]) => limit))).toBe(DEFAULT_PAGE_SIZE)
    expect(calls[11]).toEqual([550, DEFAULT_PAGE_SIZE])
  })
})
