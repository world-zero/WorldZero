// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  firstAskDue,
  installPlatform,
  markVisit,
  patchAsk,
  readAsk,
  reAskDue,
  reAskPossible,
  welcomeDue,
} from '../installAsk'

const phone = { phone: true, standalone: false, platform: 'iphone' as const }

beforeEach(() => {
  localStorage.clear()
  markVisit(false)
})

describe('install ask gating (#4052)', () => {
  it('first ask: phones in a browser, on a platform that can install, until answered', () => {
    expect(firstAskDue({}, phone)).toBe(true)
    expect(firstAskDue({}, { ...phone, phone: false })).toBe(false)
    expect(firstAskDue({}, { ...phone, standalone: true })).toBe(false)
    expect(firstAskDue({}, { ...phone, platform: null })).toBe(false)
    expect(firstAskDue({ first: 1, firstDone: true }, phone)).toBe(false)
  })

  it('re-ask needs a first ask, an earlier visit and no second answer', () => {
    expect(reAskPossible({}, phone)).toBe(false)
    expect(reAskPossible({ first: 1 }, phone)).toBe(true)
    markVisit()
    expect(reAskPossible({ first: 1 }, phone)).toBe(false)
    expect(reAskPossible({ first: 1, second: 2 }, phone)).toBe(true)
    expect(reAskPossible({ first: 1, second: 2, secondDone: true }, phone)).toBe(false)
    expect(reAskPossible({ first: 1 }, { ...phone, standalone: true })).toBe(false)
  })

  it('re-ask waits for a rating newer than the first ask, then stays until answered', () => {
    expect(reAskDue({ first: 100 }, phone, null)).toBe(false)
    expect(reAskDue({ first: 100 }, phone, 50)).toBe(false)
    expect(reAskDue({ first: 100 }, phone, 200)).toBe(true)
    expect(reAskDue({ first: 100, second: 300 }, phone, null)).toBe(true)
  })

  it('welcome shows once, only in standalone on a phone', () => {
    expect(welcomeDue({}, { phone: true, standalone: true })).toBe(true)
    expect(welcomeDue({}, { phone: true, standalone: false })).toBe(false)
    expect(welcomeDue({}, { phone: false, standalone: true })).toBe(false)
    expect(welcomeDue({ welcomed: true }, { phone: true, standalone: true })).toBe(false)
  })

  it('patches merge and survive refused storage', () => {
    patchAsk({ first: 1 })
    patchAsk({ firstDone: true })
    expect(readAsk()).toEqual({ first: 1, firstDone: true })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('refused')
    })
    expect(readAsk()).toEqual({})
    vi.restoreAllMocks()
  })

  it.each([
    ['Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1', 'iphone'],
    ['Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 CriOS/120 Mobile/15E148 Safari/604.1', null],
    ['Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36', 'android'],
    ['Mozilla/5.0 (X11; Linux x86_64) Chrome/120', null],
  ])('platform from %#', (ua, want) => {
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(ua)
    expect(installPlatform()).toBe(want)
    vi.restoreAllMocks()
  })
})

describe('install prompt is single-use (#4052)', () => {
  it('clears the held event and notifies once prompt() is spent', async () => {
    vi.resetModules()
    const m = await import('../installPrompt')
    m.captureInstallPrompt()
    const prompt = vi.fn().mockResolvedValue(undefined)
    const e = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), { prompt })
    window.dispatchEvent(e)
    const seen = vi.fn()
    m.subscribeInstallPrompt(seen)
    expect(m.heldInstallPrompt()).not.toBeNull()
    await m.promptInstall()
    expect(prompt).toHaveBeenCalledTimes(1)
    expect(m.heldInstallPrompt()).toBeNull()
    expect(seen).toHaveBeenCalled()
    await expect(m.promptInstall()).rejects.toThrow()
  })
})
