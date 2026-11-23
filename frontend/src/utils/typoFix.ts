/**
 * The owner's typo-class rule for copy (#4277). `scripts/promote_copy.py`'s
 * `is_typo_fix` is its twin; both read `scripts/copy_typo_cases.json`.
 * `blocks` mirrors difflib without autojunk: longest block, earliest in a then b.
 */

const TAGS = /\{\{[^}]*\}\}|<\/?[^<>\s]+[^<>]*>/g
const NEGATION = /(?<![a-z])(?:not|no|never)(?![a-z])|n['’]t/g

type Block = [number, number, number]

function blocks(a: string[], b: string[], alo = 0, ahi = a.length, blo = 0, bhi = b.length): Block[] {
  let best: Block = [alo, blo, 0]
  let prev = new Array<number>(bhi + 1).fill(0)
  for (let i = alo; i < ahi; i++) {
    const row = new Array<number>(bhi + 1).fill(0)
    for (let j = blo; j < bhi; j++) {
      if (a[i] !== b[j]) continue
      const k = prev[j] + 1
      row[j + 1] = k
      if (k > best[2]) best = [i - k + 1, j - k + 1, k]
    }
    prev = row
  }
  if (best[2] === 0) return []
  const [i, j, k] = best
  return [...blocks(a, b, alo, i, blo, j), best, ...blocks(a, b, i + k, ahi, j + k, bhi)]
}

function ratio(a: string[], b: string[]): number {
  if (a.length + b.length === 0) return 1
  const matched = blocks(a, b).reduce((sum, block) => sum + block[2], 0)
  return (2 * matched) / (a.length + b.length)
}

const words = (text: string) => text.split(/\s+/).filter(Boolean)
const letters = (parts: string[]) => [...parts.join(' ').toLowerCase()].filter((c) => /\p{L}/u.test(c))
const count = (re: RegExp, text: string) => (text.match(re) ?? []).length
const sameSorted = (x: string[], y: string[]) => x.slice().sort().join('\u0000') === y.slice().sort().join('\u0000')

/** `next`'s words with `changed` flagging those not carried over from `old`; no typo gating. */
export function wordDiff(old: string, next: string) {
  const a = words(old)
  const b = words(next)
  const changed = b.map(() => true)
  let i = 0
  let j = 0
  const hunks: [number, number, number, number][] = []
  for (const [ai, bj, size] of [...blocks(a, b), [a.length, b.length, 0] as Block]) {
    if (ai > i || bj > j) hunks.push([i, ai, j, bj])
    for (let k = 0; k < size; k++) changed[bj + k] = false
    i = ai + size
    j = bj + size
  }
  return { a, b, words: b, changed, hunks }
}

/**
 * Null when `next` is not a typo-class fix of `old`. Otherwise `next`'s words with
 * `changed` flagging those that differ (a pure punctuation delete flags none).
 */
export function typoDiff(old: string, next: string): { words: string[]; changed: boolean[] } | null {
  if (!sameSorted(old.match(TAGS) ?? [], next.match(TAGS) ?? [])) return null
  if (!sameSorted(old.match(/[0-9]+/g) ?? [], next.match(/[0-9]+/g) ?? [])) return null
  const { a, b, changed, hunks } = wordDiff(old, next)
  for (const [i1, i2, j1, j2] of hunks) {
    const x = letters(a.slice(i1, i2))
    const y = letters(b.slice(j1, j2))
    if (x.length === 0 && y.length === 0) continue
    if (i1 === i2 || j1 === j2 || Math.abs(x.length - y.length) > 2) return null
    // A ratio can't tell he/she apart, so short hunks must also be anagrams.
    if (ratio(x, y) < 0.75 || (x.length <= 3 && y.length <= 3 && x.slice().sort().join('') !== y.slice().sort().join('')))
      return null
    if (count(NEGATION, a.slice(i1, i2).join(' ').toLowerCase()) !== count(NEGATION, b.slice(j1, j2).join(' ').toLowerCase()))
      return null
  }
  return { words: b, changed }
}

export const isTypoFix = (old: string, next: string) => typoDiff(old, next) !== null
