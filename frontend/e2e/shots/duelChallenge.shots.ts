// Duel challenge card (/updates, one injected item) and the WOW join button.
import { test, expect } from '@playwright/test'

import { settle } from './settle'

const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const OUT = process.env.SHOT_DIR ?? 'test-results/shots'
const SIZES = { mobile: { width: 375, height: 800 }, desktop: { width: 1280, height: 900 } }

for (const viewport of ['mobile', 'desktop'] as const) {
  for (const theme of ['light', 'dark']) {
    test.describe(`duel card · ${viewport}.${theme}`, () => {
      test.use({ hasTouch: viewport === 'mobile' })
      test('shot', async ({ page }) => {
        await page.addInitScript(([k, v]) => localStorage.setItem(k, v), ['wz-theme', theme])
        await page.setViewportSize(SIZES[viewport])
        const login = await page.request.post(
          `${API}/auth/dev-login?key=duelcard-${viewport}-${theme}-${Date.now()}&name=Duel%20Bot&level=3`,
        )
        expect(login.ok(), `dev-login failed — is the backend up on ${API}?`).toBeTruthy()
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
          if (new URL(route.request().url()).pathname !== '/activity-feed') {
            return route.fulfill({ response, headers })
          }
          const body = await response.json()
          body.items = [
            {
              type: 'duel_challenge', item_key: 'duel_challenge:1', timestamp: new Date().toISOString(),
              actor_display_name: 'Ada', actor_faction_slug: 'coven', actor_avatar_url: null,
              context_faction_slug: 'coven',
              payload: {
                duel_id: 1, challenger_praxis_id: 1, challenger_character_id: 1,
                task_title: 'Build a shed', task_point_value: 40, task_faction_slug: 'coven',
              },
            },
            ...(body.items ?? []),
          ]
          await route.fulfill({ response, headers, json: body })
        })
        await page.goto('/updates')
        await expect(page.getByText(/challenged you to a duel/i).first()).toBeVisible()
        await settle(page)
        await page.screenshot({ path: `${OUT}/duel.${viewport}.${theme}.png`, animations: 'disabled' })
      })
    })
  }
}

test('wow join button', async ({ page }) => {
  await page.setViewportSize(SIZES.desktop)
  await page.request.post(`${API}/auth/dev-login?key=wowjoin-${Date.now()}&name=Wow%20Bot&level=3`)
  await page.route(`${API}/**`, async (route) => {
    const cors = {
      'access-control-allow-origin': route.request().headers().origin ?? '*',
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': '*',
      'access-control-allow-methods': '*',
    }
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors })
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), ...cors } })
  })
  await page.goto('/factions/wow')
  await settle(page)
  await page.screenshot({ path: `${OUT}/wow.join.png`, animations: 'disabled', fullPage: true })
})
