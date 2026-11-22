// Rail "Recent activity" invitation row (#4147); /me/sidebar is rewritten to carry one.
import { test, expect } from '@playwright/test'

import { settle } from './settle'

const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const OUT = process.env.SHOT_DIR ?? 'test-results/shots'

test('rail invitation row', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const key = `rail-inv-${Date.now()}`
  const login = await page.request.post(`${API}/auth/dev-login?key=${key}&name=Rail%20Bot&level=3`)
  expect(login.ok(), `dev-login failed — is the backend up on ${API}?`).toBeTruthy()
  // :3504 is not CORS-allowed, so every API answer carries its own CORS headers.
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
    if (!new URL(route.request().url()).pathname.startsWith('/me/sidebar')) {
      return route.fulfill({ response, headers })
    }
    const body = await response.json()
    body.global_activity = [
      {
        type: 'invitation_letter', item_key: 'invitation_letter:1', timestamp: new Date().toISOString(),
        actor_display_name: null, actor_faction_slug: 'coven', actor_avatar_url: null,
        context_faction_slug: 'coven', payload: { letter_id: 1, faction_slug: 'coven' },
      },
      ...body.global_activity,
    ]
    await route.fulfill({ response, headers, json: body })
  })
  await page.goto('/')
  await expect(page.getByText(/invited to join/i)).toBeVisible()
  await settle(page)
  await page.screenshot({ path: `${OUT}/rail.invitation.png`, animations: 'disabled' })
})
