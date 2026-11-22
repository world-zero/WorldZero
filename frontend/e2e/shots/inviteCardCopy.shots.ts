/** The invitation feed card on two factions' copy sheets (#4133). */
import { test, expect } from '@playwright/test'

import { settle } from './settle'

const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const OUT = process.env.SHOT_DIR ?? 'test-results/shots'
const ALL = ['handle_reports', 'edit_copy']

for (const slug of ['coven', 'snide']) {
  test(`invitation card · ${slug}`, async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 900 })
    const login = await page.request.post(`${API}/auth/dev-login?key=gating-shot&name=Gate%20Bot&level=3`)
    expect(login.ok(), `dev-login failed — is the backend up on ${API}?`).toBeTruthy()
    await page.route(`${API}/auth/me`, async (route) => {
      const me = await (await route.fetch()).json()
      await route.fulfill({ json: { ...me, is_admin: true, is_owner: true, permissions: ALL } })
    })
    await page.goto(`/admin/copy/${slug}`)
    const card = page.locator('[data-sheet-surface="FeedCardInvitationLetter"]')
    await expect(card).toBeVisible()
    await settle(page)
    await card.screenshot({ path: `${OUT}/invite.${slug}.card.png`, animations: 'disabled' })
  })
}
