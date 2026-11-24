/** An absent foe shows the placeholder as text and draws no initial in the face (#4238). */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect, vi } from 'vitest'
import '../../../i18n'
import type { DuelDetailOut, DuelSideOut } from '../../../api/duel'

vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => undefined }))

const { default: EverymenDuelSealConfirm } = await import('../EverymenDuelSealConfirm')
const { default: UaDuelSealConfirm } = await import('../UaDuelSealConfirm')

const side = (id: number, name: string, name_state: 'ok' | 'absent'): DuelSideOut =>
  ({ character_id: id, praxis_id: id, display_name: name, name_state, faction_slug: 'everymen' }) as DuelSideOut

const duel = {
  id: 5,
  status: 'pending',
  state: 'challenged',
  challenger: side(1, 'Ada', 'ok'),
  opponent: side(2, '', 'absent'),
} as unknown as DuelDetailOut

describe.each([
  ['Everymen', EverymenDuelSealConfirm],
  ['UA', UaDuelSealConfirm],
])('%s seal-confirm with an absent foe', (_name, Seal) => {
  const html = renderToStaticMarkup(
    <Seal duel={duel} viewerCharacterId={1} taskPointValue={60} onConfirm={() => {}} onCancel={() => {}} />,
  )
  it('names the foe with the placeholder', () => {
    expect(html).toContain('&lt;A Nonexistent Player&gt;')
  })
  it('draws no initial of the placeholder', () => {
    expect(html).not.toMatch(/>&lt;<\/span>/)
  })
})
