// Community header count and podium-only roster (#4063); /leaderboard is stubbed.
import { test, expect } from '@playwright/test'

import { settle } from './settle'

const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const OUT = process.env.SHOT_DIR ?? 'test-results/shots'
const SIZES = { mobile: { width: 375, height: 1200 }, desktop: { width: 1280, height: 1100 } }

const player = (id: number) => ({
  id, username: `p${id}`, display_name: `Player ${id}`, bio: '', tagline: '', avatar_url: '',
  location: '', level: 3, score: 1000 - id * 10, all_time_score: 1000 - id * 10,
  faction_slug: 'everymen', status: 'active', created_at: '2026-01-01T00:00:00Z', badges: [], invitations: [],
})

for (const viewport of ['mobile', 'desktop'] as const) {
  for (const n of [2, 20]) {
    test.describe(`community · ${viewport}.${n}`, () => {
      test.use({ hasTouch: viewport === 'mobile' })
      test('shot', async ({ page }) => {
        await page.addInitScript(() => {
          const real = window.matchMedia.bind(window)
          window.matchMedia = (query: string) => real(query.replace('(pointer: coarse)', '(min-width: 0px)'))
        })
        if (viewport === 'mobile') {
          const cdp = await page.context().newCDPSession(page)
          await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 })
        }
        await page.setViewportSize(SIZES[viewport])
        // The shots server is not on a CORS-allowed port, so the stub answers CORS itself.
        await page.route(`${API}/leaderboard**`, (route) => {
          const headers = {
            'access-control-allow-origin': route.request().headers().origin ?? '*',
            'access-control-allow-credentials': 'true',
            'access-control-allow-headers': '*',
          }
          if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
          return route.fulfill({ json: Array.from({ length: n }, (_, i) => player(i + 1)), headers })
        })
        await page.goto('/leaderboard')
        await expect(page.getByText(`${n} players`)).toBeVisible()
        await settle(page)
        await page.screenshot({ path: `${OUT}/community.${viewport}.${n}.png`, animations: 'disabled' })
      })
    })
  }
}
