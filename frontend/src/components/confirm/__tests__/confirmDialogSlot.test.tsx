/**
 * #2161 — `confirmDisabled` and `children` on the shared dialog. Truly `disabled`,
 * not `aria-disabled`: a click that gets through here is unrecoverable.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect, vi } from 'vitest'
import '../../../i18n'

vi.mock('../../../hooks/useFormFactor', () => ({ useFormFactor: () => 'desktop' }))

import ConfirmDialog from '../ConfirmDialog'

const REQUEST = {
  kind: 'delete-account',
  title: 'Delete your account',
  body: 'Type pilgrim@example.com below to confirm.',
  confirmLabel: 'Delete account',
  danger: true,
}

function markup(props: { confirmDisabled?: boolean } = {}): string {
  return renderToStaticMarkup(
    <ConfirmDialog
      request={REQUEST}
      factionSlug={null}
      onConfirm={() => {}}
      onDismiss={() => {}}
      {...props}
    >
      <p>This ends WZ Pilgrim, and 2 other lives.</p>
    </ConfirmDialog>,
  )
}

const accept = (html: string) =>
  /<button[^>]*data-testid="confirm-accept"[^>]*>/.exec(html)?.[0] ?? ''

describe('the held confirm', () => {
  it('renders the affirmative button genuinely disabled when asked', () => {
    expect(accept(markup({ confirmDisabled: true }))).toMatch(/\sdisabled(=|\s|>)/)
  })

  it('paints it with the repo disabled state rather than the live destructive fill', () => {
    expect(
      accept(markup({ confirmDisabled: true })),
      '.control-off is the only rule that says what disabled looks like',
    ).toContain('control-off')
  })

  it('leaves it live by default, so the composer confirms are unchanged', () => {
    expect(accept(markup())).not.toMatch(/\sdisabled(=|\s|>)/)
  })
})

describe('the content slot', () => {
  it('renders inside the panel, so it is inside the trap and the description', () => {
    const html = markup()
    const panel = html.indexOf('data-testid="confirm-dialog"')
    const slot = html.indexOf('This ends WZ Pilgrim')
    const footer = html.indexOf('data-testid="confirm-accept"')
    expect(panel).toBeGreaterThan(-1)
    expect(slot).toBeGreaterThan(panel)
    expect(slot, 'the slot sits above the footer, not after it').toBeLessThan(footer)
  })

  it('renders nothing extra when no caller passes one', () => {
    const bare = renderToStaticMarkup(
      <ConfirmDialog
        request={REQUEST}
        factionSlug={null}
        onConfirm={() => {}}
        onDismiss={() => {}}
      />,
    )
    expect(bare).not.toContain('This ends')
  })
})

describe('a tall sheet scrolls to its title (#3993)', () => {
  it('scrolls the overlay and anchors by auto margin, not align-items', () => {
    const html = markup()
    expect(html).toContain('fixed inset-0 z-50 flex overflow-y-auto overscroll-contain')
    expect(html).not.toContain('align-items')
    expect(html).toContain('margin:var(--sheet-margin, auto)')
  })
})

describe('hideTitle', () => {
  it('keeps the h2 as the dialog name but screen-reader only', () => {
    const html = renderToStaticMarkup(
      <ConfirmDialog
        request={{ ...REQUEST, hideTitle: true }}
        factionSlug={null}
        onConfirm={() => {}}
        onDismiss={() => {}}
      />,
    )
    const h2 = /<h2 id="([^"]+)" class="([^"]*)"[^>]*>([^<]*)<\/h2>/.exec(html)
    expect(h2?.[2]).toContain('sr-only')
    expect(h2?.[3]).toBe(REQUEST.title)
    expect(html).toContain(`aria-labelledby="${h2?.[1]}"`)
  })
})
