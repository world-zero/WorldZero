/**
 * Rendered copy → the catalog key(s) that produced it, for admin copy-edit mode.
 * The `copyRegistry` postProcessor in `i18n.ts` records every string as it
 * renders, keyed on the RENDERED value so interpolated copy resolves too.
 * One string can come from several keys ("Points" from eight), so the index
 * holds a list and an ambiguous click makes the editor choose. Recording is off
 * by default and disarming clears it. No React here (frontend/CLAUDE.md).
 */

import { paragraphsOf } from './paragraphs'

/** Namespace file + dotted key. */
export interface CopyTarget {
  ns: string
  key: string
}

/** The editor's own copy never enters the index; its "save"/"cancel" would shadow the page's. */
const EDITOR_NS = 'admin'
const EDITOR_KEY_PREFIX = 'copyEdit.'

let recording = false
const byRenderedValue = new Map<string, CopyTarget[]>()
/** Same, keyed with edge glyphs stripped: `{t('seeMore')} →` renders "See more →". */
const byBareValue = new Map<string, CopyTarget[]>()

const EDGE_GLYPHS = /^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu
const bare = (text: string) => text.replace(EDGE_GLYPHS, '')
/** `<1>`, `</1>`, `<b>`, `<br/>`. */
const TRANS_TAG = /<\/?\w+\s*\/?>/g
const HAS_WORDS = /[\p{L}\p{N}]/u

/** Disarming drops the index; it is only a cache. */
export function setCopyRecording(on: boolean): void {
  recording = on
  if (on) return
  byRenderedValue.clear()
  byBareValue.clear()
}

export function isCopyRecording(): boolean {
  return recording
}

function has(list: CopyTarget[], target: CopyTarget): boolean {
  return list.some((seen) => seen.ns === target.ns && seen.key === target.key)
}

/** Called by the i18next postProcessor for every string it renders. */
export function recordRenderedCopy(value: string, target: CopyTarget): void {
  if (!recording) return
  if (target.ns === EDITOR_NS && target.key.startsWith(EDITOR_KEY_PREFIX)) return
  const text = value.trim()
  if (!text) return
  // <Trans> values keep their component tags; the DOM text never has them.
  const plain = text.replace(TRANS_TAG, '')
  for (const entry of new Set([text, plain, ...paragraphsOf(text), ...paragraphsOf(plain)])) {
    add(byRenderedValue, entry, target)
    const stripped = bare(entry)
    if (stripped) add(byBareValue, stripped, target)
  }
}

function add(index: Map<string, CopyTarget[]>, entry: string, target: CopyTarget): void {
  const found = index.get(entry)
  if (!found) index.set(entry, [target])
  else if (!has(found, target)) found.push(target)
}

export function recordedCopyTargets(): CopyTarget[] {
  return [...byRenderedValue.values()].flat()
}

export function copyTargetsForText(text: string | null | undefined): CopyTarget[] {
  if (!text) return []
  const exact = byRenderedValue.get(text.trim())
  if (exact) return exact
  const stripped = bare(text)
  return stripped ? (byBareValue.get(stripped) ?? []) : []
}

/** Cap on the upward walk, so a miss cannot match an ancestor that merely contains the string. */
export const COPY_ANCESTOR_LIMIT = 4

function childrenOf(el: Element): Element[] {
  return el.children ? Array.from(el.children) : []
}

/**
 * The node, then its direct children, then the same for a few ancestors. The
 * child pass is needed: a click on a button's padding targets the button, whose
 * text includes icon glyphs. It only counts when the rest of the element is
 * glyphs: otherwise a player's task title would borrow its "in progress" badge's key.
 */
export function copyMatchForElement(
  start: Element | null,
): { el: Element; targets: CopyTarget[] } | null {
  let el = start
  for (let hops = 0; el && hops <= COPY_ANCESTOR_LIMIT; hops += 1) {
    const own = copyTargetsForText(el.textContent)
    if (own.length > 0) return { el, targets: own }

    const fromChildren: CopyTarget[] = []
    let rest = el.textContent ?? ''
    for (const child of childrenOf(el)) {
      const found = copyTargetsForText(child.textContent)
      if (found.length > 0) rest = rest.replace(child.textContent ?? '', '')
      for (const candidate of found) {
        if (!has(fromChildren, candidate)) fromChildren.push(candidate)
      }
    }
    if (fromChildren.length > 0 && !HAS_WORDS.test(rest)) return { el, targets: fromChildren }

    el = el.parentElement
  }
  return null
}

/**
 * The hard guard on a save. A dropped `{{…}}` is harmless (i18next just skips
 * the value), but one the template lacks, such as a typo, renders a silent gap.
 * A dropped or renamed `<Trans>` tag still loses its component. Tags are checked
 * against `template` (in force); `{{…}}` against `known` (the shipped text, so a
 * saved drop can be undone).
 */
export function missingPlaceholders(template: string, next: string, known = template): string[] {
  const tags = (s: string) => [...new Set(s.match(/<\/?\w+\s*\/?>/g) ?? [])]
  const vars = (s: string) => [...new Set(s.match(/\{\{[^}]*\}\}/g) ?? [])]
  return [
    ...tags(template).filter((t) => !next.includes(t)),
    ...vars(next).filter((v) => !known.includes(v)),
  ]
}
