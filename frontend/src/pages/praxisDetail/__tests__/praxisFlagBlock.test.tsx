/** PraxisFlagBlock: the closed card and the open form both keep a 44px tap floor. */
import { describe, it, expect } from 'vitest'
import '../../../i18n'
import { PraxisFlagBlock } from '../shared'
import { aPraxisDetailState, markup } from '../../../test/praxisDetail'
import { aPraxis } from '../../../test/fixtures'

const render = (over: Parameters<typeof aPraxisDetailState>[0]) =>
  markup(<PraxisFlagBlock state={aPraxisDetailState({ praxis: aPraxis({ can_flag: true }), ...over })} />).html

const buttons = (html: string) => html.match(/<button[^>]*>[\s\S]*?<\/button>/g) ?? []

describe('PraxisFlagBlock', () => {
  it('closed: one Flag button, no reason form, 44px floor', () => {
    const [flag, ...rest] = buttons(render({}))
    expect(rest).toEqual([])
    expect(flag).toContain('>Flag<')
    expect(flag).toMatch(/min-height:\s*44px/)
    expect(flag).toMatch(/min-width:\s*44px/)
  })

  it('open: reasons, submit and cancel all keep the floor; Flag is gone', () => {
    const html = render({ showFlagForm: true, flagReason: 'spam' })
    const all = buttons(html)
    expect(html).toContain('role="radiogroup"')
    expect(all.some((b) => b.includes('>Submit flag<'))).toBe(true)
    expect(all.some((b) => b.includes('>Cancel<'))).toBe(true)
    expect(all.some((b) => b.includes('>Flag<'))).toBe(false)
    for (const b of all) {
      expect(b).toMatch(/min-height:\s*44px/)
      expect(b).toMatch(/min-width:\s*44px/)
    }
  })
})
