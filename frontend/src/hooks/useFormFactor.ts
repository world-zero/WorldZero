import { useSyncExternalStore } from 'react'

export type FormFactor = 'mobile' | 'desktop'

// Phone = narrow AND coarse pointer (#3182); a narrow mouse window stays desktop
// down to 600px. No tablet tier.
export const MOBILE_QUERY = '(max-width: 767px) and (pointer: coarse)'

export function formFactorFor(matchesMobile: boolean): FormFactor {
  return matchesMobile ? 'mobile' : 'desktop'
}

export const PHONE_WIDTH_QUERY = '(max-width: 767px)'

const subscribeTo = (query: string) => (onChange: () => void): (() => void) => {
  const mql = window.matchMedia(query)
  mql.addEventListener('change', onChange)
  return () => mql.removeEventListener('change', onChange)
}
const subscribe = subscribeTo(MOBILE_QUERY)
const subscribeWidth = subscribeTo(PHONE_WIDTH_QUERY)

/** Width-only phone check, no pointer term. Players directory only (#3980); everything else uses useFormFactor. */
export function usePhoneWidth(): boolean {
  return useSyncExternalStore(
    subscribeWidth,
    () => window.matchMedia(PHONE_WIDTH_QUERY).matches,
    () => false,
  )
}

/** Reactive media-query form factor (no UA sniffing). */
export function useFormFactor(): FormFactor {
  return useSyncExternalStore(
    subscribe,
    () => formFactorFor(window.matchMedia(MOBILE_QUERY).matches),
    () => 'desktop', // ponytail: SSR/no-matchMedia default; desktop is the safe layout
  )
}
