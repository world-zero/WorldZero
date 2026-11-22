// @vitest-environment jsdom
/** #3966 — unknown URLs and coded 404s fall to a not-found line with a way back, never "Try refreshing". */
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/apiError'

const api = vi.hoisted(() => ({ fail: vi.fn() }))

vi.mock('../../api/tasks', () => ({ getTask: api.fail, listTasks: api.fail }))
vi.mock('../../api/praxis', () => ({ getPraxis: api.fail, getVoters: api.fail, listPraxes: api.fail }))
vi.mock('../../api/characters', () => ({ getCharacter: api.fail }))
vi.mock('../../api/comments', () => ({ listComments: () => Promise.resolve(null) }))
vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({ user: null, loading: false }),
  hadSessionLastVisit: () => false,
}))
vi.mock('../../components/Layout', () => ({ default: ({ children }: { children: React.ReactNode }) => children }))

import '../../i18n'
import App from '../../App'
import TaskDetail from '../TaskDetail'
import PraxisDetail from '../PraxisDetail'
import CharacterProfile from '../CharacterProfile'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const coded = (status: number, code: string) =>
  new ApiError(new Response(null, { status }), { detail: { code, message: 'x' } })

function open(path: string, route: string, element: React.ReactElement) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={route} element={element} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('not found', () => {
  it('an unmatched path shows the page-not-found line and a link home', async () => {
    render(
      <MemoryRouter initialEntries={['/zzz-typo']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/Page not found\./)).toBeTruthy()
    expect(screen.getByRole('link').getAttribute('href')).toBe('/')
  })

  it.each([
    ['/tasks/999999', '/tasks/:id', <TaskDetail />, 'TASK_NOT_FOUND', /Task not found\./, '/tasks'],
    ['/praxis/999999', '/praxis/:id', <PraxisDetail />, 'PRAXIS_NOT_FOUND', /Praxis not found\./, '/praxis'],
    ['/characters/999999', '/characters/:id', <CharacterProfile />, 'CHARACTER_NOT_FOUND', /Character not found\./, '/leaderboard'],
  ])('%s: a coded 404 shows not-found, a back link, no retry', async (path, route, el, code, line, back) => {
    api.fail.mockRejectedValue(coded(404, code))
    open(path, route, el)
    expect(await screen.findByText(line)).toBeTruthy()
    expect(screen.getByRole('link').getAttribute('href')).toBe(back)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('a 500 still offers Try refreshing', async () => {
    api.fail.mockRejectedValue(coded(500, 'BOOM'))
    open('/tasks/1', '/tasks/:id', <TaskDetail />)
    expect(await screen.findByText(/Try refreshing/)).toBeTruthy()
  })
})
