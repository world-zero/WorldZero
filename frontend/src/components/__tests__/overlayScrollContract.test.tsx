/**
 * #3937: the image-adjust modal scrolls from the card's top on a short (landscape) screen.
 * `align-items: center` clips the overflow off the top where nothing can reach it; the
 * overlay scrolls and the card centres with auto margins (the #3850 duel-seal pattern).
 */
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
