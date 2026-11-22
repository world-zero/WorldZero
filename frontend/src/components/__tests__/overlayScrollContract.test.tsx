// `align-items: center` clips a tall modal's top off-screen on a short (landscape) screen;
// the overlay must scroll and the card centre with auto margins (the duel-seal pattern).
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect } from 'vitest'
import '../../i18n'
import ImageEditModal from '../imageEdit/ImageEditModal'

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
