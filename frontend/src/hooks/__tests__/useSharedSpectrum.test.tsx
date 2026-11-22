// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { useRef } from 'react'
import { useSharedSpectrum } from '../useSharedSpectrum'

globalThis.ResizeObserver ??= class { observe() {} disconnect() {} unobserve() {} } as never

function Sheet() {
  const band = useRef<HTMLSpanElement>(null)
  useSharedSpectrum(band)
  return (
    <div className="spectrum-shared">
      <span ref={band} className="spectrum-rule" />
      <span data-testid="rule" className="spectrum-rule" />
    </div>
  )
}

describe('useSharedSpectrum', () => {
  it('sets the sheet width and each mark offset, and the CSS reads them', () => {
    const { container, getByTestId } = render(<Sheet />)
    const sheet = container.querySelector<HTMLElement>('.spectrum-shared')!
    expect(sheet.style.getPropertyValue('--spec-w')).toBe('0px')
    expect(getByTestId('rule').style.getPropertyValue('--spec-x')).toBe('0px')
    const css = readFileSync('src/css/06-faction-chrome-2.css', 'utf8')
    expect(css).toMatch(/\.spectrum-shared \.spectrum-rule \{[^}]*var\(--spec-w[^}]*var\(--spec-x/)
  })
})
