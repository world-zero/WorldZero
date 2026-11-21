/** Beat 6 takes its level and unlock line from the config and catalogs (rule 12): swap the config and the markup follows. */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect, vi } from 'vitest'

import '../../i18n'
import progression from '../../locales/en/progression.json'
import votes from '../../locales/en/votes.json'

const profiles = vi.hoisted(() => ({
  value: [
    { rank_key: '', unlocks: [] },
    { rank_key: 'x', unlocks: [] },
    { rank_key: 'trailhead', unlocks: [{ kind: 'ability', key: 'vote' }, { kind: 'sense', key: 'worn_paths' }] },
  ],
}))
const gate = vi.hoisted(() => ({ value: true as boolean | undefined }))
vi.mock('../../hooks/useGameConfig', () => ({
  useGameConfig: () => ({ level_profiles: profiles.value, vote_requires_received_vote: gate.value }),
}))

import Beat6 from '../onboarding/beats/Beat6'

describe('Beat 6', () => {
  it('rolls into the first level that unlocks something, and names only its abilities', () => {
    const m = renderToStaticMarkup(<Beat6 confidence={0.7} />)
    expect(m).toContain('<span>1</span><span>2</span>')
    expect(m).toContain(progression.unlocks.vote.name)
    expect(m).not.toContain(progression.unlocks.worn_paths.name)
  })

  it('states the received-vote lock only while the era has it on', () => {
    const lock = votes.chrome.receivedVoteGate
    gate.value = true
    expect(renderToStaticMarkup(<Beat6 confidence={0.7} />)).toContain(lock)
    gate.value = false
    expect(renderToStaticMarkup(<Beat6 confidence={0.7} />)).not.toContain(lock)
    gate.value = undefined
    expect(renderToStaticMarkup(<Beat6 confidence={0.7} />)).not.toContain(lock)
  })
})
