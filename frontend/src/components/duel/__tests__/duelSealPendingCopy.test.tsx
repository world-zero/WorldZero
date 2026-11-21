/** The pending seal says the post stays private and names the lapse window (#3875). */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect, vi } from 'vitest'
import '../../../i18n'
import type { GameConfigOut } from '../../../api/gameConfig'
import type { DuelDetailOut, DuelSideOut } from '../../../api/duel'

vi.mock('../../../hooks/useGameConfig', () => ({
  useGameConfig: () => ({ factions: [], duel_challenge_lapse_days: 5 }) as unknown as GameConfigOut,
}))

const { DefaultDuelSealConfirm } = await import('../DuelSealConfirm')

const side = (id: number, name: string): DuelSideOut =>
  ({ character_id: id, praxis_id: id, display_name: name, faction_slug: 'wow' }) as DuelSideOut

describe('pending duel seal copy', () => {
  it('interpolates the era lapse days and says the post stays private', () => {
    const duel = {
      id: 5,
      status: 'pending',
      challenger: side(1, 'Ada'),
      opponent: side(2, 'Rax'),
    } as unknown as DuelDetailOut
    const html = renderToStaticMarkup(
      <DefaultDuelSealConfirm
        duel={duel}
        viewerCharacterId={1}
        taskPointValue={60}
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(html).toContain('stays private until they answer')
    expect(html).toContain('within 5 days')
  })
})
