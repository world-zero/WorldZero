/** #4238: an absent player has no name, link or initial on the voter list or the byline. Seam: archetype render + bylineFaces. */
import { describe, it, expect } from 'vitest'
import { surfaceMap } from '../../../factions'
import DefaultPraxisDetail from '../archetypes/DefaultPraxisDetail'
import { bylineFaces } from '../shared'
import { authorToCharacter } from '../../../components/comments/shared'
import { aPraxis, aMember } from '../../../test/fixtures'
import { aPraxisDetailState, markup } from '../../../test/praxisDetail'
import common from '../../../locales/en/common.json'

const archetypes = { ...surfaceMap('praxisDetail'), __default__: DefaultPraxisDetail }
const voter = (over: object) => ({
  character_id: 77,
  display_name: 'Zork',
  avatar_url: '',
  faction_slug: 'na',
  value: 3,
  name_state: 'ok',
  ...over,
})

describe('voter list with an absent voter', () => {
  for (const [slug, Archetype] of Object.entries(archetypes)) {
    if (slug === 'albescent') continue
    it(`${slug} shows the placeholder and no profile link`, () => {
      const state = aPraxisDetailState({
        voters: [voter({ display_name: '', name_state: 'absent' })] as never,
      })
      const { html, text } = markup(<Archetype state={state} />)
      expect(text).toContain(common.absentPlayer.replace('<', '&lt;').replace('>', '&gt;'))
      expect(html).not.toContain('href="/characters/77"')
    })
  }
})

describe('faces for an absent player', () => {
  it('bylineFaces gives an absent author no name to take initials from', () => {
    const praxis = aPraxis({
      created_by_display_name: '',
      created_by_name_state: 'absent',
      members: [aMember({ character_display_name: '', character_name_state: 'absent' })],
    })
    expect(bylineFaces(praxis).map((f) => f.name)).toEqual([''])
  })

  it('a comment author draws no username initial', () => {
    const c = authorToCharacter({
      id: 1, username: '', display_name: '', avatar_url: '', faction_slug: 'na', name_state: 'absent',
    })
    expect(c.username).toBe('')
  })
})
