// Pending task seen by a non-proposer (#4160); /tasks answers are rewritten to be pending.
import { test, expect } from '@playwright/test'

import { settle } from './settle'

const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const OUT = process.env.SHOT_DIR ?? 'test-results/shots'

for (const faction of ['na', 'coven']) {
  test(`pending task ${faction}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    const login = await page.request.post(`${API}/auth/dev-login?key=pend-${Date.now()}&name=Pend%20Bot&level=3`)
    expect(login.ok(), `dev-login failed — is the backend up on ${API}?`).toBeTruthy()
    const pend = (t: Record<string, unknown>) => ({
      ...t, status: 'pending', signup_reason: 'task_status_closed', can_sign_up: false, primary_faction_slug: faction,
    })
    await page.route(`${API}/**`, async (route) => {
      const cors = {
        'access-control-allow-origin': route.request().headers().origin ?? '*',
        'access-control-allow-credentials': 'true',
        'access-control-allow-headers': '*',
        'access-control-allow-methods': '*',
      }
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors })
      const response = await route.fetch()
      const headers = { ...response.headers(), ...cors }
      const path = new URL(route.request().url()).pathname
      if (route.request().method() === 'GET' && /^\/tasks\/?$/.test(path)) {
        return route.fulfill({ response, headers, json: (await response.json()).map(pend) })
      }
      if (route.request().method() === 'GET' && /^\/tasks\/\d+$/.test(path)) {
        return route.fulfill({ response, headers, json: pend(await response.json()) })
      }
      return route.fulfill({ response, headers })
    })
    await page.goto('/tasks')
    await expect(page.getByText('Pending review').first()).toBeVisible()
    await settle(page)
    await page.screenshot({ path: `${OUT}/pending.card.${faction}.png`, animations: 'disabled' })
    await page.goto('/tasks/1')
    await expect(page.getByText('Pending review').first()).toBeVisible()
    await settle(page)
    await page.screenshot({ path: `${OUT}/pending.detail.${faction}.png`, animations: 'disabled' })
  })
}
