// Onboarding Terms + Welcome back cards on phones (#4186): a gutter each side.
import { test, expect } from '@playwright/test'

import { openTitle, passBeats } from '../onboardingWalk'
import { settle } from './settle'

const OUT = process.env.SHOT_DIR ?? 'test-results/shots'
test.use({ storageState: { cookies: [], origins: [] }, hasTouch: true, isMobile: true })

for (const [w, h] of [[375, 667], [390, 844], [412, 915]]) {
  for (const theme of ['light', 'dark']) {
    test(`ob cards ${w} ${theme}`, async ({ page }) => {
      test.setTimeout(120_000)
      await page.setViewportSize({ width: w, height: h })
      await page.addInitScript((t) => localStorage.setItem('wz-theme', t), theme)
      await page.route('http://localhost:8000/**', async (route) => {
        const cors = {
          'access-control-allow-origin': route.request().headers().origin ?? '*',
          'access-control-allow-credentials': 'true',
          'access-control-allow-headers': '*',
          'access-control-allow-methods': '*',
        }
        if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors })
        if (route.request().url().includes('/auth/returning-player')) {
          return route.fulfill({ headers: cors, json: { deleted_at: '2026-10-01T12:00:00Z' } })
        }
        const response = await route.fetch()
        await route.fulfill({ response, headers: { ...response.headers(), ...cors } })
      })
      await page.goto('/start/again')
      await settle(page)
      await expect(page.getByTestId('returning-body')).toBeVisible()
      await page.screenshot({ path: `${OUT}/ob-again-${w}-${theme}.png` })
      const a = await page.locator('.ob-sheet').first().boundingBox()
      expect(a!.x).toBeGreaterThan(0)
      await openTitle(page)
      await page.getByTestId('onboarding-start').click()
      await passBeats(page)
      await settle(page)
      await page.screenshot({ path: `${OUT}/ob-terms-${w}-${theme}.png` })
      const b = await page.locator('.ob-sheet').first().boundingBox()
      expect(b!.x).toBeGreaterThan(0)
      expect(w - b!.x - b!.width).toBeGreaterThan(0)
    })
  }
}
