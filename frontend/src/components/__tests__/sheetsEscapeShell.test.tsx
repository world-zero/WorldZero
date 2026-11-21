/**
 * Bottom sheets escape `ShellContent`'s stacking context (#1591). The tap-through
 * itself needs a browser; this checks each sheet portals to `document.body`.
 * `react-dom/server` refuses portals, so the throw is the proof. With no
 * `document` the tree stays inline, keeping other suites' markup intact.
 */
import type { ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, afterEach } from 'vitest'

// factionName and the sheet copy read the raw i18n instance, not a provider.
import '../../i18n'

const formFactorMock = vi.fn(() => 'desktop')
vi.mock('../../hooks/useFormFactor', () => ({
  useFormFactor: () => formFactorMock(),
}))

vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({ applyUser: () => {} }),
}))

// Keeps the API transport out of the module graph.
vi.mock('../../api/me', () => ({
  getMyCharacters: async () => [],
  setActiveCharacter: async () => ({}),
}))

import ShellContent from '../layout/ShellContent'
import ConfirmDialog from '../confirm/ConfirmDialog'
import FeedBankFullModal from '../feed/FeedBankFullModal'
import CharacterSwitcherSheet from '../CharacterSwitcherSheet'
import { OptionOverlay } from '../ui/FilterBar/OptionPicker'
import { drawAtRoot } from '../ui/drawAtRoot'
import type { FilterFacet } from '../ui/FilterBar/filterState'
import BottomSheet from '../ui/BottomSheet'
import YouSheet from '../layout/YouSheet'
import type { CharacterOut } from '../../api/auth'
import { ruleBodies, stripComments } from '../../utils/__tests__/cssVars'

import { readIndexCss } from '../../test/indexCss'

const css = stripComments(readIndexCss())
const body = (css: string, sel: string) => ruleBodies(css, sel).join('\n')

const REACT_PORTAL = Symbol.for('react.portal')

/** A portal's runtime fields, which `@types/react`'s `ReactPortal` lacks. */
interface PortalShape {
  $$typeof: symbol
  containerInfo: unknown
}

/** `isValidContainer` reads only `nodeType`. */
const FAKE_BODY = { nodeType: 1 } as unknown as HTMLElement

function withDocument<T>(run: () => T): T {
  vi.stubGlobal('document', { body: FAKE_BODY })
  try {
    return run()
  } finally {
    vi.unstubAllGlobals()
  }
}

const FACET: FilterFacet = {
  key: 'type',
  label: 'Type',
  options: [
    { value: 'nudge', label: 'Nudge' },
    { value: 'notice', label: 'Notice' },
  ],
  selected: ['nudge'],
  onChange: () => {},
}

function switcher(formFactor: 'mobile' | 'desktop'): string {
  formFactorMock.mockReturnValue(formFactor)
  return renderToStaticMarkup(
    <MemoryRouter>
      <CharacterSwitcherSheet open activeCharacterId={1} onClose={() => {}} />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  formFactorMock.mockReturnValue('desktop')
})

describe('drawAtRoot', () => {
  it('hands the overlay back untouched when there is no document', () => {
    const overlay = <div data-test="overlay" />
    expect(drawAtRoot(overlay)).toBe(overlay)
    expect(renderToStaticMarkup(drawAtRoot(overlay) as ReactElement)).toContain('data-test="overlay"')
  })

  it('portals the overlay to document.body when there is one', () => {
    const portal = withDocument(() => drawAtRoot(<div />)) as unknown as PortalShape
    expect(portal.$$typeof).toBe(REACT_PORTAL)
    expect(portal.containerInfo).toBe(FAKE_BODY)
  })
})

describe('CharacterSwitcherSheet', () => {
  it('portals — the shell can no longer cap it under the tab bar', () => {
    expect(() => withDocument(() => switcher('mobile'))).toThrow(/[Pp]ortal/)
  })

  it('still renders its markup inline in the DOM-less harness', () => {
    const html = switcher('mobile')
    expect(html).toContain('role="dialog"')
    expect(html).toContain('aria-modal="true"')
    // Rows load in an effect (see characterPaths.test.tsx); this is the chrome.
    expect(html).toContain('Your characters')
  })

  it('wears the switcher panel class on the phone', () => {
    expect(switcher('mobile')).toContain('switcher-sheet')
  })

  it('draws on the shared chassis', () => {
    expect(switcher('mobile')).toContain('sheet-scrim')
  })
})

describe('sheet paint (rule bodies)', () => {
  it('takes its scrim and shadow from tokens, never a raw rgba', () => {
    expect(body(css, ':where(.sheet-scrim)')).toMatch(/background:\s*var\(--color-overlay-strong\)/)
    expect(body(css, ':where(.sheet-panel)')).toMatch(/box-shadow:[^;]*var\(--color-cast-shadow\)/)
    expect(body(css, '.sheet-grab') + body(css, '.switcher-sheet')).not.toMatch(/rgba?\(|#[0-9a-f]{3,8}\b/i)
  })

  it('clears the tab bar on the switcher through --switcher-bottom', () => {
    expect(body(css, '.switcher-sheet')).toMatch(/padding-bottom:\s*var\(--switcher-bottom,/)
  })

  it('pays the bottom inset once: the chassis does, an above-tab-bar panel does not', () => {
    expect(body(css, ':where(.sheet-panel)')).toMatch(/padding:[^;]*env\(safe-area-inset-bottom\)/)
    const above = body(css, '.sheet-above-tabs > .sheet-panel')
    expect(above).toMatch(/bottom:\s*var\(--tab-bar-clearance\)/)
    expect(above).toMatch(/padding-bottom:\s*var\(--space-sm\)/)
  })

  it('pays the top inset once: the strip holds it, the phone region drops it while the strip is up', () => {
    expect(body(css, 'html[data-mod-strip]')).toMatch(/--region-inset-top:\s*0px/)
    expect(renderToStaticMarkup(<ShellContent isMobile sidebarCollapsed={false} onToggleSidebar={() => {}}>x</ShellContent>)).toContain(
      'var(--space-lg) + var(--region-inset-top, env(safe-area-inset-top))',
    )
  })

  it('pays the top inset on the mod strip', () => {
    expect(body(css, '.mod-strip')).toMatch(/padding:\s*calc\(var\(--space-xs\) \+ env\(safe-area-inset-top\)\)/)
  })
})

describe('BottomSheet switches', () => {
  const sheet = (props: { aboveTabBar?: boolean; grab?: boolean }) =>
    renderToStaticMarkup(
      <BottomSheet label="L" scrimLabel="S" onClose={() => {}} {...props}>
        x
      </BottomSheet>,
    )

  it('aboveTabBar adds sheet-above-tabs; the default covers the tab bar', () => {
    expect(sheet({ aboveTabBar: true })).toContain('sheet-above-tabs')
    expect(sheet({})).not.toContain('sheet-above-tabs')
  })

  it('grab={false} drops the handle', () => {
    expect(sheet({})).toContain('sheet-grab')
    expect(sheet({ grab: false })).not.toContain('sheet-grab')
  })

  it('keeps the scrim out of the tab order', () => {
    expect(sheet({})).toMatch(/<button[^>]*tabindex="-1"[^>]*sheet-scrim/)
  })
})

describe('YouSheet', () => {
  it('is a labelled dialog stopping above the tab bar', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <YouSheet
          character={{ id: 1, username: 'ada', display_name: 'Ada', faction_slug: 'ua' } as unknown as CharacterOut}
          pending={0}
          isAdmin={false}
          onClose={() => {}}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('role="dialog"')
    expect(html).toContain('sheet-above-tabs')
    expect(html).toContain('Ada')
  })
})

describe('OptionOverlay', () => {
  it('portals the phone sheet', () => {
    expect(() =>
      withDocument(() =>
        renderToStaticMarkup(<OptionOverlay facet={FACET} isSheet onDone={() => {}} />),
      ),
    ).toThrow(/[Pp]ortal/)
  })

  it('leaves the desktop popover exactly where its anchor is', () => {
    // Positioned against its trigger, so a portal would tear it off.
    const html = withDocument(() =>
      renderToStaticMarkup(<OptionOverlay facet={FACET} isSheet={false} onDone={() => {}} />),
    )
    expect(html).toContain('filter-factions__popover')
    expect(html).not.toContain('sheet-scrim')
  })

  it('still renders the sheet and its scrim inline in the DOM-less harness', () => {
    const html = renderToStaticMarkup(<OptionOverlay facet={FACET} isSheet onDone={() => {}} />)
    expect(html).toContain('sheet-scrim')
    expect(html).toContain('filter-factions__sheet')
    expect(html).toContain('aria-checked="true"')
  })
})

describe('modals', () => {
  const confirm = (
    <ConfirmDialog
      request={{ kind: 'k', title: 'T', body: 'B', confirmLabel: 'Go' }}
      factionSlug={null}
      onConfirm={() => {}}
      onDismiss={() => {}}
    />
  )
  const bankFull = (
    <FeedBankFullModal
      title="Full"
      body="B"
      cancelLabel="No"
      options={[]}
      busy={false}
      error=""
      onDismiss={() => {}}
    />
  )

  it.each([
    ['ConfirmDialog', confirm, 'role="dialog"'],
    ['FeedBankFullModal', bankFull, 'role="dialog"'],
  ])('%s portals with a document and renders inline without one', (_n, el, marker) => {
    expect(() => withDocument(() => renderToStaticMarkup(el))).toThrow(/[Pp]ortal/)
    expect(renderToStaticMarkup(el)).toContain(marker)
  })
})
