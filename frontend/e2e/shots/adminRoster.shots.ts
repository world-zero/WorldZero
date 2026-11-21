/**
 * The owner's Admins roster (#3847). Roster routes are stubbed, so the shared
 * backend's code and data never matter: the dev account only signs in.
 */
import { test, expect } from '@playwright/test'

import { settle } from './settle'

const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const OUT = process.env.SHOT_DIR ?? 'test-results/shots'
const SIZES = { mobile: { width: 375, height: 1500 }, desktop: { width: 1280, height: 900 } }
const ROSTER = [
  { username: 'molly', display_name: 'Molly', is_owner: true, suspended: false, permissions: [] },
  { username: 'wren', display_name: 'Wren', is_owner: false, suspended: false, permissions: ['handle_reports', 'review_proposals', 'edit_copy'] },
  { username: 'pell', display_name: 'Pell', is_owner: false, suspended: true, permissions: ['ban_suspend'] },
]

for (const viewport of ['mobile', 'desktop'] as const) {
  for (const theme of ['light', 'dark']) {
    test.describe(`roster · ${viewport}.${theme}`, () => {
      test.use({ hasTouch: viewport === 'mobile' })
      test('shot', async ({ page }) => {
        await page.addInitScript(([key, value]) => localStorage.setItem(key, value), ['wz-theme', theme])
        // Headless Chromium never matches (pointer: coarse); without this the phone shot is desktop chrome.
        await page.addInitScript(() => {
          const real = window.matchMedia.bind(window)
          window.matchMedia = (query: string) => real(query.replace('(pointer: coarse)', '(min-width: 0px)'))
        })
        if (viewport === 'mobile') {
          const cdp = await page.context().newCDPSession(page)
          await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 })
        }
        await page.setViewportSize(SIZES[viewport])
        const login = await page.request.post(`${API}/auth/dev-login?key=roster-shot&name=Roster%20Bot&level=3`)
        expect(login.ok(), `dev-login failed — is the backend up on ${API}?`).toBeTruthy()
        await page.route(`${API}/auth/me`, async (route) => {
          const me = await (await route.fetch()).json()
          await route.fulfill({ json: { ...me, is_admin: true, is_owner: true } })
        })
        await page.route(`${API}/admin/admins`, (route) => route.fulfill({ json: ROSTER }))
        await page.route(`${API}/admin/characters**`, (route) => route.fulfill({ json: [] }))
        await page.goto('/admin/people')
        await page.getByRole('button', { name: /Admins \(3\)/ }).dispatchEvent('click')
        await expect(page.getByText('Owner — every permission')).toBeVisible()
        await settle(page)
        await page.screenshot({ path: `${OUT}/roster.${viewport}.${theme}.png`, animations: 'disabled' })
      })
    })
  }
}
