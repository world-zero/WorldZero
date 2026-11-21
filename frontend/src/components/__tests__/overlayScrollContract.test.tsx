/**
 * #3937: centred modals scroll from the card's top on a short (landscape) screen.
 * `align-items: center` clips the overflow off the top where nothing can reach it; the
 * overlay scrolls and the card centres with auto margins (the #3850 duel-seal pattern).
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect } from 'vitest'
import '../../i18n'
import ImageEditModal from '../imageEdit/ImageEditModal'
import { CollabSuccess } from '../collab/CollabSuccess'

describe('ImageEditModal overlay', () => {
  const html = renderToStaticMarkup(
    <ImageEditModal file={new File([''], 'a.png', { type: 'image/png' })} onConfirm={() => {}} onCancel={() => {}} />,
  )
  it('scrolls and centres the card with auto margins', () => {
    const overlay = html.slice(0, html.indexOf('>'))
    expect(overlay).toContain('overflow-y:auto')
    expect(overlay).not.toContain('align-items')
    expect(html).toContain('margin:auto')
  })
})

describe('CollabSuccess overlay', () => {
  const html = renderToStaticMarkup(
    <CollabSuccess members={[]} currentCharacterId={1} factionSlug="wow" onContinue={() => {}} />,
  )
  it('scrolls and centres the card with my-auto', () => {
    const overlay = html.slice(0, html.indexOf('>'))
    expect(overlay).toContain('overflow-y-auto')
    expect(overlay).not.toContain('items-center')
    expect(html).toContain('my-auto')
  })
})
