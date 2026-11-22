import { onSwMessage } from './utils/requestsBus'

// After `load` so the worker never competes with first paint; production only so dev HMR is never served from a cache.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('message', onSwMessage)
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
