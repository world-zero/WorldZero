/** The pending seal says the post stays private and names the lapse window (#3875). */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect, vi } from 'vitest'
import '../../../i18n'
import type { GameConfigOut } from '../../../api/gameConfig'
import type { DuelDetailOut, DuelSideOut } from '../../../api/duel'

let config: GameConfigOut | undefined
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => config }))
const loaded = { factions: [], duel_challenge_lapse_days: 5 } as unknown as GameConfigOut

const { DefaultDuelSealConfirm } = await import('../DuelSealConfirm')

const side = (id: number, name: string): DuelSideOut =>
  ({ character_id: id, praxis_id: id, display_name: name, faction_slug: 'wow' }) as DuelSideOut

const render = () => {
  const duel = {
    id: 5,
    status: 'pending',
    challenger: side(1, 'Ada'),
    opponent: side(2, 'Rax'),
  } as unknown as DuelDetailOut
  return renderToStaticMarkup(
    <DefaultDuelSealConfirm
      duel={duel}
      viewerCharacterId={1}
      taskPointValue={60}
      onConfirm={() => {}}
      onCancel={() => {}}
    />,
  )
}

describe('pending duel seal copy', () => {
  it('interpolates the era lapse days and says the post stays private', () => {
    config = loaded
    const html = render()
    expect(html).toContain('stays private until they answer')
    expect(html).toContain('within 5 days')
  })

  it('promises no lapse when the era never lapses duels', () => {
    config = { ...loaded, duel_challenge_lapse_days: null } as unknown as GameConfigOut
    const html = render()
    expect(html).toContain('stays private until they answer')
    expect(html).not.toContain('within')
    expect(html).not.toContain('never answer')
  })

  it('drops the number, not a hole, while /game-config is unloaded', () => {
    config = undefined
    const html = render()
    expect(html).toContain('stays private until they answer')
    expect(html).not.toContain('within')
  })
})
