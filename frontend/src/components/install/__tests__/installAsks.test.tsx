// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const m = vi.hoisted(() => ({
  get: vi.fn(),
  feed: vi.fn(),
  first: vi.fn(),
  turnOn: vi.fn(),
  block: vi.fn(),
  subscribed: vi.fn(),
}))
vi.mock('../../../api/client', () => ({ apiGet: m.get }))
vi.mock('../../../api/activityFeed', () => ({ getActivityFeed: m.feed }))
vi.mock('../../../utils/firstPraxis', () => ({ isFirstPraxis: m.first }))
vi.mock('../../push/askedPush', () => ({ turnOnAskedPush: m.turnOn }))
vi.mock('../../push/PushAsk', () => ({ default: () => 'PUSH_ASK' }))
vi.mock('../../../auth/AuthContext', () => ({
  useAuth: () => ({ user: { character: { id: 7, display_name: 'Agent Teacup' } } }),
}))
vi.mock('../../../utils/pushSubscribe', () => ({ pushBlock: m.block, deviceSubscribed: m.subscribed }))

import '../../../i18n'
import { readFileSync } from 'node:fs'
import FirstPraxisAsk from '../FirstPraxisAsk'
import HomeInstallAsks from '../HomeInstallAsks'
import InstallFlow from '../InstallFlow'
import { INSTALL_ASK_KEY, markVisit, patchAsk, readAsk } from '../../../utils/installAsk'
import { captureInstallPrompt } from '../../../utils/installPrompt'

const IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'
const ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36'

function env(ua: string, { phone = true, standalone = false } = {}) {
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(ua)
  window.matchMedia = vi.fn((q: string) => ({
    matches: q.includes('standalone') ? standalone : phone,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
}

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  m.first.mockResolvedValue(true)
  m.block.mockReturnValue('ok')
  m.subscribed.mockResolvedValue(false)
  m.get.mockResolvedValue({ data: { vapid_public_key: 'k' } })
  m.feed.mockResolvedValue({ items: [] })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.dispatchEvent(new Event('appinstalled'))
})

describe('under the first praxis', () => {
  it('a phone gets the install sheet and never PushAsk', async () => {
    env(IPHONE)
    render(<FirstPraxisAsk praxisId={5} />)
    expect(await screen.findByText('Can I live on your home screen?')).toBeTruthy()
    expect(screen.queryByText('PUSH_ASK')).toBeNull()
    expect(readAsk().first).toBeTypeOf('number')
  })

  it('desktop keeps PushAsk', () => {
    env(IPHONE, { phone: false })
    render(<FirstPraxisAsk praxisId={5} />)
    expect(screen.getByText('PUSH_ASK')).toBeTruthy()
  })

  it('not the first praxis, or already standalone: no sheet', async () => {
    env(IPHONE)
    m.first.mockResolvedValue(false)
    render(<FirstPraxisAsk praxisId={5} />)
    await waitFor(() => expect(m.first).toHaveBeenCalled())
    expect(screen.queryByTestId('install-ask')).toBeNull()
    cleanup()
    env(IPHONE, { standalone: true })
    render(<FirstPraxisAsk praxisId={5} />)
    await act(async () => {})
    expect(screen.queryByTestId('install-ask')).toBeNull()
  })

  it('Not yet records the answer and names Settings', async () => {
    env(IPHONE)
    render(<FirstPraxisAsk praxisId={5} />)
    fireEvent.click(await screen.findByText('Not yet'))
    expect(screen.getByText('No rush.')).toBeTruthy()
    expect(readAsk().firstDone).toBe(true)
  })
})

describe('InstallFlow', () => {
  it('iPhone: Show me how walks Share, Add, Add, done', () => {
    env(IPHONE)
    render(<InstallFlow platform="iphone" onAnswered={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Show me how'))
    expect(screen.getByText('Tap Share')).toBeTruthy()
    fireEvent.click(screen.getByText('Found it'))
    fireEvent.click(screen.getByText('Tapped it'))
    fireEvent.click(screen.getByText('Added'))
    expect(screen.getByText('Open me from your home screen')).toBeTruthy()
  })

  it('Android without Chrome\'s event shows the manual steps', () => {
    env(ANDROID)
    render(<InstallFlow platform="android" onAnswered={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Show me how'))
    expect(screen.getByText('Tap ⋮, then Install app')).toBeTruthy()
  })

  it('Android with the held event: one tap calls prompt()', async () => {
    env(ANDROID)
    captureInstallPrompt()
    const prompt = vi.fn().mockResolvedValue(undefined)
    const ev = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), { prompt })
    act(() => void window.dispatchEvent(ev))
    render(<InstallFlow platform="android" onAnswered={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Move me in'))
    await screen.findByText("I'm the WØ on your home screen")
    expect(prompt).toHaveBeenCalled()
  })

  it('the re-ask: either button answers for good', () => {
    env(IPHONE)
    const answered = vi.fn()
    render(<InstallFlow reask platform="iphone" onAnswered={answered} onClose={vi.fn()} />)
    expect(screen.getByText('Someone rated your praxis. I knocked.')).toBeTruthy()
    fireEvent.click(screen.getByText('Stop asking'))
    expect(answered).toHaveBeenCalledTimes(1)
    expect(screen.getByText("Got it. I won't ask again.")).toBeTruthy()
  })
})

describe('Home: housewarming and the one re-ask', () => {
  it('standalone first open: housewarming once; yes turns the asked rows on', async () => {
    env(IPHONE, { standalone: true })
    m.turnOn.mockResolvedValue('ok')
    render(<HomeInstallAsks />)
    expect(await screen.findByText("Oh, it's NICE in here.")).toBeTruthy()
    expect(screen.getByText(/Thanks for the room, Agent Teacup/)).toBeTruthy()
    fireEvent.click(screen.getByText('Yes, knock'))
    await screen.findByText('Knock knock.')
    expect(m.turnOn).toHaveBeenCalledWith('k')
    expect(readAsk().welcomed).toBe(true)
    cleanup()
    render(<HomeInstallAsks />)
    await act(async () => {})
    expect(screen.queryByTestId('housewarming')).toBeNull()
  })

  it('no housewarming where push cannot turn on', async () => {
    env(IPHONE, { standalone: true })
    m.block.mockReturnValue('denied')
    render(<HomeInstallAsks />)
    await act(async () => {})
    expect(screen.queryByTestId('housewarming')).toBeNull()
  })

  const rated = (at: number) => m.feed.mockResolvedValue({ items: [{ timestamp: new Date(at).toISOString() }] })

  it('re-ask: only after a rating newer than the first ask, in a later visit, outside standalone', async () => {
    env(IPHONE)
    patchAsk({ first: Date.now() - 1000, firstDone: true })
    rated(Date.now())
    render(<HomeInstallAsks />)
    expect(await screen.findByText('Someone rated your praxis. I knocked.')).toBeTruthy()
    expect(readAsk().second).toBeTypeOf('number')
  })

  it.each([
    ['no first ask', () => {}],
    ['same visit as the first ask', () => (patchAsk({ first: 1 }), markVisit())],
    ['a rating older than the ask', () => patchAsk({ first: Date.now() })],
    ['already answered', () => patchAsk({ first: 1, second: 2, secondDone: true })],
  ])('re-ask stays away: %s', async (_name, setup) => {
    env(IPHONE)
    setup()
    rated(Date.now() - 5000)
    if (_name === 'same visit as the first ask') rated(Date.now())
    render(<HomeInstallAsks />)
    await act(async () => {})
    expect(screen.queryByTestId('install-ask')).toBeNull()
    expect(localStorage.getItem(INSTALL_ASK_KEY)?.includes('"second":') ?? false).toBe(_name === 'already answered')
  })

  it('re-ask never shows in standalone (the housewarming is that visit)', async () => {
    env(IPHONE, { standalone: true })
    patchAsk({ first: 1, welcomed: true })
    rated(Date.now())
    render(<HomeInstallAsks />)
    await act(async () => {})
    expect(screen.queryByTestId('install-ask')).toBeNull()
    expect(m.feed).not.toHaveBeenCalled()
  })
})

describe('reduced motion', () => {
  it('stills every pose, crumb, confetti and pop to its resting frame', () => {
    const css = readFileSync('src/components/install/installAsk.css', 'utf8')
    const block = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(block).toMatch(/\.wzi-wisp \*[^{]*\{[^}]*animation: none !important/)
    expect(block).toMatch(/\.wzi-crumbs span/)
    expect(block).toMatch(/\.wzi-confetti span/)
    expect(block).toMatch(/\.wzi-pop/)
  })
})
