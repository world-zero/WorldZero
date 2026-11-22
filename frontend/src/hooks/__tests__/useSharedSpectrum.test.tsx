// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { useRef } from 'react'
import { useSharedSpectrum } from '../useSharedSpectrum'

globalThis.ResizeObserver ??= class { observe() {} disconnect() {} unobserve() {} } as never

function Sheet() {
  const band = useRef<HTMLSpanElement>(null)
  useSharedSpectrum(band)
  return (
    <div data-testid="sheet" className="spectrum-shared">
      <span ref={band} className="spectrum-rule" />
      <span data-testid="rule" className="spectrum-rule" />
    </div>
  )
}

describe('useSharedSpectrum', () => {
  it('gives the sheet its width and each mark its offset from the sheet', () => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return { left: this.dataset.testid === 'rule' ? 60 : 10 } as DOMRect
    })
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(300)
    const { getByTestId } = render(<Sheet />)
    expect(getByTestId('sheet').style.getPropertyValue('--spec-w')).toBe('300px')
    expect(getByTestId('rule').style.getPropertyValue('--spec-x')).toBe('50px')
  })
})
