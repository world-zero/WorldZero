// @vitest-environment jsdom
/** `CopyEditor` mounted with effects: arming must not loop, Revert must revert (#3081). */
import { Profiler } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Trans, useTranslation } from 'react-i18next'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { deleteCopyOverride, putCopyOverride } from '../../../api/copy'
import { ApiError } from '../../../api/apiError'
import i18n, { overriddenKeys } from '../../../i18n'
import CopyEditor, { shippedValue } from '../CopyEditor'
import { MARK } from '../copyProbe'

vi.mock('../../../api/copy', () => ({
  putCopyOverride: vi.fn(),
  deleteCopyOverride: vi.fn(),
}))

const NS = 'common'
const KEY = 'brand'

function Page() {
  const { t } = useTranslation(NS)
  return <p>{t(KEY)}</p>
}

beforeEach(() => {
  // jsdom has no matchMedia. Desktop.
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
  vi.mocked(deleteCopyOverride).mockResolvedValue(undefined)
  i18n.addResource('en', NS, KEY, 'Overridden Zero')
  overriddenKeys.add(`${NS}:${KEY}`)
})
afterEach(() => {
  vi.unstubAllGlobals()
  cleanup()
  i18n.addResource('en', NS, KEY, shippedValue(NS, KEY))
})

describe('CopyEditor, mounted', () => {
  it('settles after arming instead of looping', async () => {
    let renders = 0
    render(
      <Profiler id="editor" onRender={() => (renders += 1)}>
        <CopyEditor />
      </Profiler>,
    )
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')

    await new Promise((resolve) => setTimeout(resolve, 50))
    const settled = renders
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(renders).toBe(settled)
    expect(settled).toBeLessThan(10)
  })

  it('Revert puts the shipped wording back', async () => {
    render(
      <>
        <Page />
        <CopyEditor />
      </>,
    )
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')

    fireEvent.click(screen.getByText('Overridden Zero'))
    fireEvent.click(await screen.findByText('revert to default'))

    await waitFor(() => expect(i18n.getResource('en', NS, KEY)).toBe(shippedValue(NS, KEY)))
    expect(deleteCopyOverride).toHaveBeenCalledWith(NS, KEY)
    expect(shippedValue(NS, KEY)).not.toBe('Overridden Zero')
  })

  it('a stray page click keeps an unsaved draft, and cancel clears the notice', async () => {
    render(
      <>
        <Page />
        <span>not copy</span>
        <CopyEditor />
      </>,
    )
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')
    fireEvent.click(screen.getByText('Overridden Zero'))
    const box = await screen.findByLabelText('Replacement wording')
    fireEvent.change(box, { target: { value: 'My unsaved words' } })

    fireEvent.click(screen.getByText('not copy'))

    expect(screen.getByLabelText('Replacement wording')).toHaveProperty('value', 'My unsaved words')
    expect(screen.getByRole('status').textContent).toMatch(/unsaved/)
    fireEvent.click(screen.getByText('cancel'))
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('a save that started from stale wording shows theirs and keeps the draft', async () => {
    const conflict = new ApiError(new Response(null, { status: 409 }), {
      detail: { code: 'COPY_OVERRIDE_CHANGED', message: 'changed', params: { current: 'Their Zero' } },
    })
    vi.mocked(putCopyOverride).mockRejectedValueOnce(conflict)
    vi.mocked(putCopyOverride).mockResolvedValueOnce({ ns: NS, key: KEY, value: 'My Zero' })
    render(
      <>
        <Page />
        <CopyEditor />
      </>,
    )
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')
    fireEvent.click(screen.getByText('Overridden Zero'))
    fireEvent.change(await screen.findByLabelText('Replacement wording'), { target: { value: 'My Zero' } })

    fireEvent.click(screen.getByText('save'))
    expect(await screen.findByText(/Someone else changed this/)).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('Their Zero')
    expect(vi.mocked(putCopyOverride).mock.calls[0][0]).toEqual({ ns: NS, key: KEY, value: 'My Zero', base: 'Overridden Zero' })
    expect(i18n.getResource('en', NS, KEY)).toBe('Their Zero')
    expect(screen.getByLabelText('Replacement wording')).toHaveProperty('value', 'My Zero')

    // Saving again is a deliberate overwrite of the wording they now see.
    fireEvent.click(screen.getByText('save'))
    await waitFor(() => expect(i18n.getResource('en', NS, KEY)).toBe('My Zero'))
    expect(vi.mocked(putCopyOverride).mock.calls[1][0]).toMatchObject({ base: 'Their Zero' })
  })
})


function SameWording() {
  const { t } = useTranslation(['common', 'home', 'feed'])
  return (
    <>
      <a href="/tasks">{t('common:nav.tasks')}</a>
      <span>{t('home:signedIn.browse.tabs.tasks')}</span>
      <i>{t('feed:taskCard.pointsUnit', { count: 2 })}</i>
      <b>{t('common:leaderboard.points')}</b>
    </>
  )
}

describe('CopyEditor, one wording from several keys', () => {
  it('opens the key that renders in the clicked spot, without asking', async () => {
    const { container } = render(
      <>
        <SameWording />
        <CopyEditor />
      </>,
    )
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')

    const opened = (selector: string) => {
      fireEvent.click(container.querySelector(selector)!)
      const key = screen.queryByText(/^\w+:[\w.]+$/)?.textContent
      fireEvent.click(screen.getByText('cancel'))
      return key
    }
    expect(opened('a')).toBe('common:nav.tasks')
    expect(opened('span')).toBe('home:signedIn.browse.tabs.tasks')
    // Its rival is plural-only: no string of its own, so the forms get marked.
    expect(opened('b')).toBe('common:leaderboard.points')
    expect(screen.queryByText(/Several keys/)).toBeNull()

    fireEvent.click(container.querySelector('i')!)
    expect(screen.getByText(/form for each count/)).toBeTruthy()
    expect(container.textContent).not.toContain(MARK)
  })
})

describe('CopyEditor, <Trans> copy', () => {
  it('opens the key when the bold child is clicked', async () => {
    i18n.addResource('en', NS, 'transProbe', 'Standing · <1>card-carrying</1>')
    render(
      <>
        <p>
          <Trans i18nKey={'transProbe' as 'brand'} ns={NS} components={{ 1: <b /> }} />
        </p>
        <CopyEditor />
      </>,
    )
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')
    fireEvent.click(screen.getByText('card-carrying'))
    expect(await screen.findByText(`${NS}:transProbe`)).toBeTruthy()
    expect((screen.getByLabelText('Replacement wording') as HTMLTextAreaElement).value).toContain('<1>')
  })
})

describe('CopyEditor, edit box over the spot (#3453)', () => {
  const open = async (mobile: boolean, rect = new DOMRect(30, 50, 200, 24)) => {
    vi.stubGlobal('matchMedia', () => ({
      matches: mobile,
      addEventListener: () => {},
      removeEventListener: () => {},
    }))
    render(
      <>
        <Page />
        <CopyEditor />
      </>,
    )
    const spot = screen.getByText('Overridden Zero')
    spot.getBoundingClientRect = () => rect
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')
    fireEvent.click(spot)
    return (await screen.findByLabelText('Replacement wording')) as HTMLTextAreaElement
  }

  it('desktop: the box takes focus once placed', async () => {
    const box = await open(false)
    expect(document.activeElement).toBe(box)
  })

  it('a spot too narrow, or off screen, keeps the panel textarea', async () => {
    expect((await open(false, new DOMRect(30, 50, 20, 24))).style.position).not.toBe('fixed')
    cleanup()
    expect((await open(false, new DOMRect(30, -100, 200, 24))).style.position).not.toBe('fixed')
  })

  it('follows the spot on scroll (window or ancestor) and resize', async () => {
    const box = await open(false)
    const spot = screen.getByText('Overridden Zero', { selector: 'p' })
    for (const [top, fire] of [
      [80, () => fireEvent.scroll(window)],
      [90, () => fireEvent.scroll(spot.parentElement!)],
      [100, () => fireEvent(window, new Event('resize'))],
    ] as const) {
      spot.getBoundingClientRect = () => new DOMRect(30, top, 200, 24)
      fire()
      await waitFor(() => expect(box.style.top).toBe(`${top}px`))
    }
  })

  it('without field-sizing it gets a row per line', async () => {
    const box = await open(false)
    fireEvent.change(box, { target: { value: 'one\n\nthree' } })
    expect(box.rows).toBe(3)
  })

  it('closing a key picked from a chooser does not refocus an older spot', async () => {
    const { container } = render(
      <>
        <SameWording />
        <p id="both">
          <SameWording />
        </p>
        <button>elsewhere</button>
        <CopyEditor />
      </>,
    )
    const link = container.querySelector('a')!
    link.getBoundingClientRect = () => new DOMRect(30, 50, 200, 24)
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')
    fireEvent.click(link)
    await screen.findByLabelText('Replacement wording')
    fireEvent.click(screen.getByText('cancel'))
    await waitFor(() => expect(document.activeElement).toBe(link))

    screen.getByText('elsewhere').focus()
    fireEvent.click(container.querySelector('#both')!)
    fireEvent.click(await screen.findByText(/common:nav.tasks/, { selector: 'button' }))
    expect(((await screen.findByLabelText('Replacement wording')) as HTMLTextAreaElement).style.position).not.toBe('fixed')
    fireEvent.click(screen.getByText('cancel'))
    expect(document.activeElement).toBe(screen.getByText('elsewhere'))
  })

  it('desktop: the textarea sits at the clicked text', async () => {
    const box = await open(false)
    expect(box.style.position).toBe('fixed')
    expect([box.style.left, box.style.top, box.style.minWidth]).toEqual(['30px', '50px', '200px'])
  })

  it('phone: it stays in the panel', async () => {
    expect((await open(true)).style.position).not.toBe('fixed')
  })

  it('each spot opens in its own typography, not the first one opened', async () => {
    const real = getComputedStyle
    vi.stubGlobal('getComputedStyle', (el: Element) => {
      const cs = real(el)
      const big = el.tagName === 'A'
      return { ...cs, font: big ? '30px serif' : '10px serif', color: big ? 'red' : 'blue' }
    })
    render(
      <>
        <Page />
        <a href="/tasks">{i18n.t('common:nav.tasks')}</a>
        <CopyEditor />
      </>,
    )
    const rect = () => new DOMRect(30, 50, 200, 24)
    for (const el of [screen.getByText('Overridden Zero'), screen.getByText(i18n.t('common:nav.tasks'))])
      el.getBoundingClientRect = rect
    fireEvent.click(screen.getByText('edit copy'))
    await screen.findByText('stop editing copy')

    fireEvent.click(screen.getByText('Overridden Zero'))
    expect(((await screen.findByLabelText('Replacement wording')) as HTMLTextAreaElement).style.color).toBe('blue')
    fireEvent.click(screen.getByText(i18n.t('common:nav.tasks')))
    const box = (await screen.findByLabelText('Replacement wording')) as HTMLTextAreaElement
    expect([box.style.fontSize, box.style.color]).toEqual(['30px', 'red'])
  })
})
