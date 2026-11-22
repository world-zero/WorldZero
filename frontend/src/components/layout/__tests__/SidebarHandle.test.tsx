/**
 * #4117: the fold arrow is an aria-hidden SVG chevron (a text guillemet's ink
 * sits low in its box), flipped by `collapsed`.
 * #4131: the handle draws no pending badge; Updates in the NavBar owns it.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect, vi } from 'vitest'
import '../../../i18n'

vi.mock('../Sidebar', () => ({ default: () => null, panelStyle: {} }))

import SidebarHandle from '../SidebarHandle'

function render(collapsed: boolean): string {
  return renderToStaticMarkup(<SidebarHandle collapsed={collapsed} onToggle={() => {}} />)
}

describe('SidebarHandle', () => {
  it('draws the arrow as an aria-hidden SVG whose direction follows `collapsed`', () => {
    const open = render(false)
    const folded = render(true)
    expect(open).toMatch(/<svg[^>]*aria-hidden="true"/)
    expect(folded).toMatch(/<svg[^>]*aria-hidden="true"/)
    expect(open).not.toContain('scaleX(-1)')
    expect(folded).toContain('scaleX(-1)')
    expect(open).not.toMatch(/[‹›]/)
  })

  it('names the control for each state', () => {
    expect(render(true)).toContain('aria-label="Expand sidebar"')
    expect(render(true)).toContain('aria-expanded="false"')
    expect(render(false)).toContain('aria-label="Collapse sidebar"')
    expect(render(false)).toContain('aria-expanded="true"')
  })
})
