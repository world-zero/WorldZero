import { afterEach, expect, it } from 'vitest'
import type { FactionOut } from '../../../api/factions'
import { setAlbescentRevealed } from '../../../utils/factions'
import { proposeFactionOptions } from '../useProposeTask'

// GET /factions returns Albescent to everyone (ADR-0082).
const fetched = [{ slug: 'albescent' }, { slug: 'ua' }] as FactionOut[]

afterEach(() => setAlbescentRevealed(false))

it('offers Albescent only to a viewer who has had it revealed', () => {
  expect(proposeFactionOptions(fetched)).toEqual(['na', 'ua'])

  setAlbescentRevealed(true)
  expect(proposeFactionOptions(fetched)).toEqual(['na', 'ua', 'albescent'])
})
