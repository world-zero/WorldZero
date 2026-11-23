import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import { isTypoFix, typoDiff } from '../typoFix'

const cases: [string, string, boolean][] = JSON.parse(
  readFileSync(new URL('../../../../scripts/copy_typo_cases.json', import.meta.url), 'utf8'),
)

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
