// @vitest-environment jsdom
/** Seam: the console as `/auth/me` describes the caller — rail, landing, MOD count and in-page controls follow `permissions` (#3847). */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_PERMISSIONS, aTask } from '../../../test/fixtures'
import type { FlaggedPraxisOut, Permission } from '../../../api/admin'

const auth = vi.hoisted(() => ({ user: { is_admin: true, is_owner: false, permissions: [] as string[] } }))
const api = vi.hoisted(() => ({
  getFlaggedPraxes: vi.fn(async () => [{}, {}]),
  getFlaggedComments: vi.fn(async () => [{}]),
  getMessages: vi.fn(async () => [{}, {}, {}, {}]),
  getPendingTasks: vi.fn(async () => [{}, {}, {}, {}, {}]),
  getOverview: vi.fn(async () => ({ praxis: 38, active_tasks: 10, accounts: 21, characters: 27 })),
  getAllTasks: vi.fn(async () => [aTask({ id: 1, title: 'Walk Barefoot', status: 'active' })]),
  getTaskIdsWithHistory: vi.fn(async () => []),
  adminPatchTask: vi.fn(async () => ({})),
  updateTaskStatus: vi.fn(async () => ({})),
}))
vi.mock('../../../api/admin', () => api)
vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => ({ user: auth.user, loading: false }), hadSessionLastVisit: () => true }))
vi.mock('../../../auth/AdminModeContext', () => ({ useAdminMode: () => ({ adminMode: false, toggleAdminMode: () => {} }) }))
vi.mock('../../../components/Layout', () => ({ default: () => 'PLAYER LAYOUT' }))
vi.mock('../consolePages', () => ({
  ReportsPage: () => 'ReportsPage',
  PraxisPage: () => 'PraxisPage',
  EraPage: () => 'EraPage',
  ModLogPage: () => 'ModLogPage',
}))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => ({ level_thresholds: [0, 10], factions: [] }) }))

import App from '../../../App'
import ModControl from '../../../components/admin/ModControl'
import AuthorRow from '../AuthorRow'
import TasksTab from '../TasksTab'
import TaskPanel from '../TaskPanel'

const holding = (...permissions: Permission[]) => {
  auth.user = { is_admin: true, is_owner: false, permissions }
}
const owner = () => {
  auth.user = { is_admin: true, is_owner: true, permissions: ALL_PERMISSIONS }
}
const at = (path: string, node = <App />) => render(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>)
const railLinks = async () =>
  within(await screen.findByRole('navigation', { name: 'Admin' }))
    .getAllByRole('link')
    .map((a) => a.textContent?.replace(/\d+$/, ''))

beforeEach(() => holding('handle_reports'))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('an admin with only handle_reports', () => {
  it('sees only the pages that permission opens, plus the mod log', async () => {
    at('/admin/reports')
    expect(await railLinks()).toEqual(['← Back to World Zero', 'Reports', 'Praxis', 'Mod log'])
    expect(screen.queryByText('Danger')).toBeNull()
  })

  it('is sent from a page it may not open to the first one it may', async () => {
    at('/admin/era')
    expect(await screen.findByText('ReportsPage')).toBeTruthy()
    expect(screen.queryByText('EraPage')).toBeNull()
  })

  it('counts only reports on the MOD button, and never asks for the other queues', async () => {
    at('/', <ModControl />)
    expect(await screen.findByRole('button', { name: 'Mod, 3 waiting' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Mod, 3 waiting' }))
    expect(screen.queryByText('Messages')).toBeNull()
    expect(screen.queryByText('Task proposals')).toBeNull()
    expect(api.getMessages).not.toHaveBeenCalled()
    expect(api.getPendingTasks).not.toHaveBeenCalled()
  })

  it('gets no ban, suspend or People link on a flagged author', () => {
    const praxis = { created_by_display_name: 'Junk', author_username: 'junk', author_status: 'active', author_account_status: 'active' } as FlaggedPraxisOut
    at('/', <AuthorRow praxis={praxis} confirming={null} onAsk={vi.fn()} onCancel={vi.fn()} onModerate={vi.fn()} onViewAccount={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Remove all their flagged/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Ban|Suspend|Open in People/ })).toBeNull()
  })
})

describe('an admin with only manage_tasks', () => {
  it('loads Tasks without the reads it may not make, and gets no import or Proposals', async () => {
    holding('manage_tasks')
    at('/admin/tasks', <TasksTab />)
    expect(await screen.findByText('Walk Barefoot')).toBeTruthy()
    expect(api.getPendingTasks).not.toHaveBeenCalled()
    expect(api.getTaskIdsWithHistory).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Import CSV…' })).toBeNull()
    expect(screen.queryByText('Proposals')).toBeNull()
  })
})

describe('the owner', () => {
  it('sees every page and every queue in the count', async () => {
    owner()
    at('/admin/reports')
    expect(await railLinks()).toEqual([
      '← Back to World Zero',
      'Reports',
      'Messages',
      'Task proposals',
      'Praxis',
      'Tasks',
      'People',
      'Small world',
      'Mod log',
      'Faction copy',
      'Level-up copy',
      'Taunt copy',
      'Copy proposals',
      'Roll into a new era…',
    ])
    cleanup()
    at('/', <ModControl />)
    expect(await screen.findByRole('button', { name: 'Mod, 12 waiting' })).toBeTruthy()
  })
})

describe('the task panel without manage_tasks', () => {
  const panel = (status: 'pending' | 'deleted') => {
    const onChanged = vi.fn()
    at('/', <TaskPanel task={aTask({ id: 5, title: 'Walk', status })} factions={[]} proposal={null} onChanged={onChanged} onDeleted={vi.fn()} onClose={vi.fn()} />)
    return onChanged
  }

  it('approves an edited proposal with review_proposals alone: no PATCH, no error', async () => {
    holding('review_proposals')
    const onChanged = panel('pending')
    const title = screen.getByLabelText('Title') as HTMLInputElement
    expect(title.readOnly).toBe(true)
    fireEvent.change(title, { target: { value: 'Edited anyway' } })
    fireEvent.click(screen.getByRole('button', { name: 'activate' }))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(api.updateTaskStatus).toHaveBeenCalledWith(5, 'active', undefined)
    expect(api.adminPatchTask).not.toHaveBeenCalled()
    expect(screen.queryByText(/error/i)).toBeNull()
  })

  it('restores a deleted task with delete_import_tasks alone', async () => {
    holding('delete_import_tasks')
    const onChanged = panel('deleted')
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Edited anyway' } })
    fireEvent.click(screen.getByRole('button', { name: 'restore as pending' }))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(api.updateTaskStatus).toHaveBeenCalledWith(5, 'pending', undefined)
    expect(api.adminPatchTask).not.toHaveBeenCalled()
  })
})
