import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect } from 'vitest'
import '../../i18n'
import type { CharacterOut } from '../../api/auth'
import { CharacterSwitcherRows } from '../CharacterSwitcherSheet'

const life = (id: number, pending_requests_count: number) =>
  ({ id, username: `u${id}`, display_name: `L${id}`, faction_slug: 'coven', pending_requests_count }) as unknown as CharacterOut

describe('switcher count mark (#3776)', () => {
  const html = renderToStaticMarkup(
    <CharacterSwitcherRows lives={[life(1, 3), life(2, 0)]} activeCharacterId={2} onSelect={() => {}} />,
  )
  it('marks a life with requests waiting', () => {
    expect(html).toContain('data-testid="switcher-waiting-1"')
    expect(html).toContain('3 requests waiting')
  })
  it('leaves a life with none unmarked', () => {
    expect(html).not.toContain('switcher-waiting-2')
  })
})
