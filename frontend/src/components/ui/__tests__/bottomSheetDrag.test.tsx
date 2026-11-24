// @vitest-environment jsdom
import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import BottomSheet from '../BottomSheet'

afterEach(cleanup)

function pull(dy: number) {
  const onClose = vi.fn()
  render(
    <BottomSheet label="You" scrimLabel="Close" onClose={onClose}>
      <p>row</p>
    </BottomSheet>,
  )
  const grab = document.querySelector('.sheet-grab')!
  const panel = document.querySelector<HTMLElement>('.sheet-panel')!
  fireEvent.pointerDown(grab, { clientY: 100, pointerId: 1 })
  fireEvent.pointerMove(grab, { clientY: 100 + dy, pointerId: 1 })
  const midDrag = panel.style.transform
  fireEvent.pointerUp(grab, { clientY: 100 + dy, pointerId: 1 })
  return { onClose, midDrag, after: panel.style.transform }
}

it('pulling the grab handle well down closes the sheet (#4292)', () => {
  const { onClose, midDrag } = pull(150)
  expect(midDrag).toBe('translateY(150px)')
  expect(onClose).toHaveBeenCalledOnce()
})

it('a short pull snaps back and keeps the sheet open', () => {
  const { onClose, after } = pull(30)
  expect(onClose).not.toHaveBeenCalled()
  expect(after).toBe('')
})
