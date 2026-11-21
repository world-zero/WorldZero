/** The install asks' platform facts, kept off the components so a test can drive them. */

export interface InstallPromptEvent extends Event {
  prompt(): Promise<void>
}

let held: InstallPromptEvent | null = null
const listeners = new Set<() => void>()

/** Chrome fires this once, early; hold it from boot or a late-mounting Home misses it. */
export function captureInstallPrompt(): void {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    held = e as InstallPromptEvent
    listeners.forEach((l) => l())
  })
  window.addEventListener('appinstalled', () => {
    held = null
    listeners.forEach((l) => l())
  })
}

export function subscribeInstallPrompt(l: () => void): () => void {
  listeners.add(l)
  return () => void listeners.delete(l)
}

export const heldInstallPrompt = (): InstallPromptEvent | null => held

export function isStandalone(): boolean {
  return (
    typeof window !== 'undefined' && window.matchMedia?.('(display-mode: standalone)').matches === true ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}

/** iPhone Safari only: other iOS browsers (CriOS, FxiOS, EdgiOS) cannot add to the home screen. */
export function isIphoneSafari(): boolean {
  const ua = navigator.userAgent
  return /iPhone|iPod/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua)
}
