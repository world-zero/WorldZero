/** Fixtures for `local/no-translucent-overlay-ground` (#3945), linted through the real config. */
import { ESLint } from 'eslint'
import { beforeAll, describe, expect, it } from 'vitest'

const RULE = 'local/no-translucent-overlay-ground'

let eslint: ESLint

beforeAll(() => {
  eslint = new ESLint()
})

const reports = async (code: string): Promise<boolean> => {
  const [result] = await eslint.lintText(code, {
    filePath: 'src/overlayGroundFixture.tsx',
    warnIgnored: false,
  })
  return result.messages.some((m) => m.ruleId === RULE)
}

const dialog = (style: string, child = '') =>
  `export const A = () => <div role="dialog" style={{ ${style} }}>${child}</div>`

describe('local/no-translucent-overlay-ground flags a see-through panel root', () => {
  it('flags a dialog on --color-bg-surface', async () => {
    expect(await reports(dialog("background: 'var(--color-bg-surface)'"))).toBe(true)
  })

  it('flags the -alt token, translucent in dark', async () => {
    expect(await reports(dialog("background: 'var(--color-bg-surface-alt)'"))).toBe(true)
  })

  it('flags backgroundColor', async () => {
    expect(await reports(dialog("backgroundColor: 'var(--color-bg-surface)'"))).toBe(true)
  })

  it('flags the JSX passed straight to drawAtRoot', async () => {
    expect(
      await reports(
        "export const A = () => drawAtRoot(<div style={{ background: 'var(--color-bg-surface)' }} />)",
      ),
    ).toBe(true)
  })

  it('resolves a same-file identifier bound to JSX, and a string const', async () => {
    expect(
      await reports(
        "const G = 'var(--color-bg-surface)'\nexport const A = () => { const o = <div style={{ background: G }} />; return drawAtRoot(o) }",
      ),
    ).toBe(true)
  })
})

describe('local/no-translucent-overlay-ground stays silent otherwise', () => {
  it('allows a dialog on --color-bg-page', async () => {
    expect(await reports(dialog("background: 'var(--color-bg-page)'"))).toBe(false)
  })

  it('never flags a descendant of a solid panel', async () => {
    expect(
      await reports(
        dialog(
          "background: 'var(--color-bg-page)'",
          "<i style={{ background: 'var(--color-bg-surface-alt)' }} />",
        ),
      ),
    ).toBe(false)
  })

  it('allows a surface-painted element that is not an overlay', async () => {
    expect(
      await reports(
        "export const A = () => <div style={{ background: 'var(--color-bg-surface)' }} />",
      ),
    ).toBe(false)
  })
})
