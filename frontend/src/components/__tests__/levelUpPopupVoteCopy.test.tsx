/** The Vote ability states the received-vote lock only while the era has it on (#4056). */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect, vi } from 'vitest'
import '../../i18n'
import progression from '../../locales/en/progression.json'

const gate = vi.hoisted(() => ({ value: true }))
vi.mock('../../hooks/useGameConfig', () => ({
  useGameConfig: () => ({ vote_requires_received_vote: gate.value }),
}))

import LevelUpPopup from '../LevelUpPopup'

const render = () =>
  renderToStaticMarkup(
    <LevelUpPopup level={1} rankKey="trailhead" abilities={[{ key: 'vote', kind: 'ability' }]} onContinue={() => {}} />,
  )

describe('LevelUpPopup vote ability', () => {
  it('uses the gated wording when the gate is on and the open wording when off', () => {
    gate.value = true
    expect(render()).toContain(progression.unlocks.vote.desc)
    gate.value = false
    const html = render()
    expect(html).toContain(progression.unlocks.vote.descOpen.replace("'", '&#x27;'))
    expect(html).not.toContain('Once another quester')
  })
})
