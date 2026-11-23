import { describe, expect, it } from 'vitest'

import shared from '../../../../scripts/copy_typo_cases.json'
import { isTypoFix, typoDiff } from '../typoFix'

const cases = shared as [string, string, boolean][]

describe('isTypoFix', () => {
  it.each(cases)('%j -> %j is %s', (old, next, expected) => {
    expect(isTypoFix(old, next)).toBe(expected)
  })

  it('marks the changed words of the fix', () => {
    expect(typoDiff('Join the comminty.', 'Join the community.')).toEqual({
      words: ['Join', 'the', 'community.'],
      changed: [false, false, true],
    })
  })
})
