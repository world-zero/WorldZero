// Band-skin collab footer (#4194): GET /praxis/900 and /tasks/7 are stubbed; nothing else is.
import { test, expect } from '@playwright/test'

import { settle } from './settle'

const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const OUT = process.env.SHOT_DIR ?? 'test-results/shots'
const PROPOSED_AT = '2026-08-17T10:00:00Z'

const member = (id: number, over = {}) => ({
  id, praxis_id: 900, character_id: id, character_display_name: `M${id}`, character_avatar_url: '',
  has_approved: false, is_done: false, joined_at: '2026-01-01T00:00:00Z', nudged_at: null,
  nudge_again_at: null, approved_at: null, ...over,
})

for (const faction of ['coven', 'snide']) {
  for (const live of [false, true]) {
    for (const [label, size] of [['desktop', { width: 1280, height: 1000 }], ['phone', { width: 375, height: 800 }]] as const) {
      test(`collab footer ${faction} ${live ? 'live' : 'propose'} ${label}`, async ({ page }) => {
        await page.setViewportSize(size)
        const login = await page.request.post(
          `${API}/auth/dev-login?key=band-${faction}&name=Band%20Bot&level=3&faction=${faction}`,
        )
        expect(login.ok(), `dev-login failed — is the backend up on ${API}?`).toBeTruthy()
        const me = await (await page.request.get(`${API}/auth/me`)).json()
        const meId: number = me.character.id
        const praxis = {
          id: 900, task_id: 7, task_title: 'A Very Human Thing', task_faction_slug: faction,
          task_point_value: 20, type: 'collab', status: live ? 'pending' : 'in_progress',
          submit_proposed_at: live ? PROPOSED_AT : null, moderation_status: 'visible', duel_id: null,
          created_by_id: meId, title: 'I helped a stranger', body_text: '## What I did\n\nCaught the papers.',
          members: [member(meId), member(meId + 1000, { has_approved: live })],
          invites: [], media_items: [], score: 20, metatask_points: 0, display_multiplier: 1,
          points_from_votes: 0, habit_bonus_points: 0, rival_bonus_points: 0,
        }
        const task = {
          id: 7, title: 'A Very Human Thing', description: 'Do a small honest thing.', point_value: 20,
          level_required: 1, status: 'active', task_type: 'standard', primary_faction_slug: faction,
          metatask_faction_slug: null, allowed_modes: ['solo', 'collab', 'duel'],
          eligible_for_current_user: true, can_sign_up: true,
        }
        await page.route(`${API}/**`, async (route) => {
          const cors = {
            'access-control-allow-origin': route.request().headers().origin ?? '*',
            'access-control-allow-credentials': 'true',
            'access-control-allow-headers': '*',
            'access-control-allow-methods': '*',
          }
          const req = route.request()
          if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors })
          const path = new URL(req.url()).pathname
          if (req.method() === 'GET' && path === '/praxes/900') return route.fulfill({ headers: cors, json: praxis })
          if (req.method() === 'GET' && path === '/tasks/7') return route.fulfill({ headers: cors, json: task })
          const response = await route.fetch()
          await route.fulfill({ response, headers: { ...response.headers(), ...cors } })
        })
        await page.goto('/praxis/900/edit')
        const links = page.getByRole('button', { name: /part/i }).first()
        await expect(links).toBeVisible({ timeout: 15_000 })
        await settle(page)
        const boxes = await page
          .locator('[data-testid="collab-secondaries"] button, [data-testid="composer-primary"]')
          .evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON()))
        for (let i = 0; i < boxes.length; i++) {
          for (let j = i + 1; j < boxes.length; j++) {
            const a = boxes[i], b = boxes[j]
            const overlap = a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom
            expect(overlap, `controls ${i} and ${j} overlap`).toBe(false)
          }
        }
        expect(boxes.length).toBeGreaterThanOrEqual(2)
        const noScroll = await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        )
        expect(noScroll).toBe(true)
        await page.locator('[data-testid="collab-secondaries"]').evaluate((e) => e.scrollIntoView({ block: 'center' }))
        await page.screenshot({ path: `${OUT}/collab.${faction}.${live ? 'live' : 'propose'}.${label}.png`, animations: 'disabled' })
      })
    }
  }
}
