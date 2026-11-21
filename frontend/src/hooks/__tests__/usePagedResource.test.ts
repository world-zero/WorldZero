/** #645 — `usePagedResource`'s offset-paging math. */
import { describe, it, expect } from 'vitest'
import { pageHasMore, loadPage, windowFor, nextWindow, DEFAULT_PAGE_SIZE } from '../usePagedResource'
import { runResource } from '../useResource'

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

describe('windowFor / nextWindow — filter changes and load-more races', () => {
  const win = { key: 'a', prior: [1, 2], offset: 2 }

  it('keeps the window while the deps key is unchanged', () => {
    expect(windowFor(win, 'a')).toBe(win)
  })

  it('restarts at row 0 when the key changes without any setter (URL nav, debounced q)', () => {
    expect(windowFor(win, 'b')).toEqual({ key: 'b', prior: [], offset: 0 })
  })

  it('loadMore is a no-op while a load is in flight, even on a full old page', () => {
    expect(nextWindow('b', [1, 2], true)).toBeNull()
    expect(nextWindow('a', null, false)).toBeNull()
  })

  it('loadMore advances from what is loaded, under the current key', () => {
    expect(nextWindow('a', [1, 2, 3], false)).toEqual({ key: 'a', prior: [1, 2, 3], offset: 3 })
  })

  it('a response cancelled by a key change never lands', async () => {
    const landed: number[][] = []
    await runResource(() => Promise.resolve([9]), {
      onStart: () => {}, onData: (d) => landed.push(d), onError: () => {}, onSettle: () => {},
    }, () => true)
    expect(landed).toEqual([])
  })
})
