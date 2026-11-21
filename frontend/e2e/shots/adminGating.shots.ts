/**
 * The console as a one-box admin and as the owner (#3847). `/auth/me` and the
 * admin reads are stubbed, so the shared backend only signs the bot in.
 */
import { test, expect } from '@playwright/test'

import { settle } from './settle'

const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const OUT = process.env.SHOT_DIR ?? 'test-results/shots'
const ALL = ['handle_reports', 'ban_suspend', 'review_proposals', 'manage_tasks', 'delete_import_tasks', 'read_messages', 'edit_copy', 'small_world', 'roll_era']
const WHO = {
  reports: { is_owner: false, permissions: ['handle_reports'] },
  owner: { is_owner: true, permissions: ALL },
}
const message = { id: 1, name: 'Ada', email: 'ada@example.org', message: 'Hi', is_archived: false, created_at: '2026-11-20T10:00:00Z' }

for (const [who, grants] of Object.entries(WHO)) {
  for (const theme of ['light', 'dark']) {
    test.describe(`console · ${who}.mobile.${theme}`, () => {
      test.use({ hasTouch: true })
      test('shot', async ({ page }) => {
        await page.addInitScript(([key, value]) => localStorage.setItem(key, value), ['wz-theme', theme])
        // Headless Chromium never matches (pointer: coarse); without this the phone shot is desktop chrome.
        await page.addInitScript(() => {
          const real = window.matchMedia.bind(window)
          window.matchMedia = (query: string) => real(query.replace('(pointer: coarse)', '(min-width: 0px)'))
        })
        await page.setViewportSize({ width: 375, height: 900 })
        const login = await page.request.post(`${API}/auth/dev-login?key=gating-shot&name=Gate%20Bot&level=3`)
        expect(login.ok(), `dev-login failed — is the backend up on ${API}?`).toBeTruthy()
        await page.route(`${API}/auth/me`, async (route) => {
          const me = await (await route.fetch()).json()
          await route.fulfill({ json: { ...me, is_admin: true, ...grants } })
        })
        await page.route(`${API}/admin/**`, (route) => {
          const path = new URL(route.request().url()).pathname
          if (path.endsWith('/overview')) return route.fulfill({ json: { accounts: 21, characters: 27, active_tasks: 10, praxis: 38, votes: 90 } })
          if (path.endsWith('/messages')) return route.fulfill({ json: [message, { ...message, id: 2 }] })
          if (path.endsWith('/tasks/pending')) return route.fulfill({ json: [] })
          if (path.endsWith('/mod-log')) return route.fulfill({ json: { items: [], total: 0 } })
          return route.fulfill({ json: [] })
        })
        await page.goto('/admin/reports')
        // The layout closes the menu on mount; open it once the page has drawn.
        await expect(page.getByRole('tablist', { name: 'Report type' })).toBeVisible()
        await page.getByRole('button', { name: 'Menu' }).dispatchEvent('click')
        await expect(page.getByRole('navigation', { name: 'Admin' }).getByRole('link', { name: 'Mod log' })).toBeVisible()
        await settle(page)
        await page.screenshot({ path: `${OUT}/gating.${who}.mobile.${theme}.png`, animations: 'disabled' })
      })
    })
  }
}
