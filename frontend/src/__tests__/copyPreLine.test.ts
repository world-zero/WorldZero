/** #4293: live copy edits keep their line breaks app-wide; markdown opts out. */
import { readFileSync } from 'node:fs'
import { describe, it, expect } from 'vitest'

const css = (f: string) => readFileSync(new URL(`../css/${f}`, import.meta.url), 'utf8')
const decl = (src: string, selector: string) =>
  new RegExp(`(?:^|\\s)${selector.replace(/[>*.]/g, '\\$&')}\\s*\\{([^}]*)\\}`, 'm').exec(src)?.[1]

describe('app-wide pre-line', () => {
  it('body > * keeps line breaks', () => {
    expect(decl(css('04-component-layer-base.css'), 'body > *')).toMatch(/white-space:\s*pre-line/)
  })

  it('.md-flow resets to normal', () => {
    expect(decl(css('05-component-layer-components.css'), '.md-flow')).toMatch(/white-space:\s*normal/)
  })
})
