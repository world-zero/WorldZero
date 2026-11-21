/** When the wisp may ask a phone player to install (#4052): at most two install asks, one welcome. */
import { isIphoneSafari } from './installPrompt'

export const INSTALL_ASK_KEY = 'wz:installAsk'

export interface AskState {
  /** ms when the first ask was first shown. */
  first?: number
  firstDone?: true
  /** ms when the re-ask was first shown. */
  second?: number
  secondDone?: true
  welcomed?: true
}

export type InstallPlatform = 'iphone' | 'android'

// ponytail: localStorage, not per account; no settings field exists. Move server-side if one lands.
export function readAsk(): AskState {
  try {
    return JSON.parse(localStorage.getItem(INSTALL_ASK_KEY) ?? '{}') as AskState
  } catch {
    return {}
  }
}

export function patchAsk(patch: AskState): AskState {
  const next = { ...readAsk(), ...patch }
  try {
    localStorage.setItem(INSTALL_ASK_KEY, JSON.stringify(next))
  } catch {
    // Refused storage: the ask may return next load.
  }
  return next
}

// Module state, not storage: a page load is a visit, and a new storage key would need cookie-card copy.
let askedThisVisit = false

/** The re-ask must not land in the same visit as the first ask. */
export function markVisit(asked = true): void {
  askedThisVisit = asked
}

/** iPhone Safari or an Android browser; any other phone browser cannot be installed from, so it is never asked. */
export function installPlatform(): InstallPlatform | null {
  if (isIphoneSafari()) return 'iphone'
  return /Android/.test(navigator.userAgent) ? 'android' : null
}

interface Env {
  readonly phone: boolean
  readonly standalone: boolean
  readonly platform: InstallPlatform | null
}

const inBrowser = (e: Env) => e.phone && !e.standalone && e.platform !== null

export function firstAskDue(s: AskState, e: Env): boolean {
  return inBrowser(e) && !s.firstDone
}

/** Everything but the rating: the caller fetches the feed only once this holds. */
export function reAskPossible(s: AskState, e: Env): boolean {
  if (!inBrowser(e) || s.first === undefined || s.secondDone) return false
  return s.second !== undefined || !askedThisVisit
}

/** A rating that landed after the first ask; once the re-ask has been shown it stays until answered. */
export function reAskDue(s: AskState, e: Env, ratedAt: number | null): boolean {
  if (!reAskPossible(s, e)) return false
  return s.second !== undefined || (ratedAt !== null && ratedAt > (s.first ?? 0))
}

export function welcomeDue(s: AskState, e: Pick<Env, 'phone' | 'standalone'>): boolean {
  return e.phone && e.standalone && !s.welcomed
}
