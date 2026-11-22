import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import '../../i18n'
import { PlayerLink } from '../PlayerName'
import { playerLabel } from '../../utils/playerLabel'

const html = (state: 'ok' | 'suspended' | 'absent') =>
  renderToStaticMarkup(
    <MemoryRouter>
      <PlayerLink state={state} name="Wren" to="/characters/7" />
    </MemoryRouter>,
  )

describe('player names (#4238)', () => {
  it('links an ok name', () => {
    expect(html('ok')).toContain('href="/characters/7"')
    expect(html('ok')).toContain('Wren')
  })

  it('shows a suspended name unlinked, with the suffix', () => {
    expect(html('suspended')).not.toContain('href')
    expect(html('suspended')).toContain('Wren (Suspended)')
  })

  it('shows an absent player as the placeholder, unlinked and unnamed', () => {
    const markup = html('absent')
    expect(markup).not.toContain('href')
    expect(markup).not.toContain('Wren')
    expect(markup).toContain('&lt;A Nonexistent Player&gt;')
  })

  it('labels outside a component the same way', () => {
    expect(playerLabel('Wren', 'absent')).toBe('<A Nonexistent Player>')
    expect(playerLabel('Wren', 'suspended')).toBe('Wren (Suspended)')
  })
})
