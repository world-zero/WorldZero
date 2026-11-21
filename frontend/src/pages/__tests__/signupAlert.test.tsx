// @vitest-environment jsdom
/** A failed card sign-up is announced: every surface that shows `signupMsg` wraps it in role=alert. Seam: the page + its banner. */
import { render, screen, cleanup } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const MSG = 'Could not sign up (test)'
const signup = vi.hoisted(() => ({ msg: null as string | null }))

vi.mock('../../hooks/useTaskSignup', () => ({
  useTaskSignup: () => ({ signupMsg: signup.msg, handleSignup: async () => {} }),
}))
vi.mock('../tasks/useTasks', () => ({
  useTasks: () => ({
    user: null, tasks: [{}], loading: false, error: null, taskType: 'metatask', hasMore: false,
    loadMore: () => {}, signupMsg: signup.msg, handleSignup: async () => {}, displayMultiplierFor: () => 1,
  }),
}))
vi.mock('../tasks/TaskFilterBar', () => ({ default: () => null, TaskListEmpty: () => null }))
vi.mock('../tasks/ProposeTaskLink', () => ({ default: () => null }))
vi.mock('../../components/metataskSeal/MetataskSeal', () => ({ default: () => null }))
vi.mock('../factionDetail/useFactionDetail', () => ({
  useFactionDetail: () => ({
    loading: false, fetchError: null, faction: { slug: 'everymen' }, members: [], tasks: [], recentPraxis: [],
    signupMsg: signup.msg,
  }),
}))
vi.mock('../../factions', () => ({ surfaceMap: () => ({ na: () => null }) }))
vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({ user: { character: { id: 1, faction_slug: 'everymen' } }, applyUser: () => {} }),
}))
vi.mock('../../api/me', () => ({ getMyCharacters: async () => [], setActiveCharacter: async () => {} }))
vi.mock('../../api/praxis', () => ({ listPraxes: async () => [] }))
vi.mock('../../api/tasks', () => ({ listTasks: async () => [] }))
vi.mock('../fieldDesk/useFieldDeskHome', () => ({ useFieldDeskHome: () => null }))
vi.mock('../../hooks/useFormFactor', () => ({ useFormFactor: () => 'desktop' }))
vi.mock('../../hooks/useSidebarPanels', () => ({ useSidebarPanels: () => ({ active_praxes: [] }) }))
vi.mock('../../hooks/useRosterChoice', () => ({ rosterOffersAChoice: () => false }))
vi.mock('../../hooks/useResource', () => ({
  useResource: () => ({ data: [{ id: 1, display_name: 'Ana', faction_slug: 'everymen' }, [], []], loading: false, error: null }),
}))
vi.mock('../../hooks/useGameConfig', () => ({ useGameConfig: () => null }))
vi.mock('../../utils/levelTrack', () => ({ levelTrack: () => null }))
vi.mock('../characterProfile/useOwnProposals', () => ({ useOwnProposals: () => ({ tasks: [], actions: {}, error: null }) }))
vi.mock('../characterProfile/FactionProfileBody', () => ({ default: () => null }))
vi.mock('../../components/backdrop/BackdropContext', () => ({ useFactionBackdrop: () => {} }))
vi.mock('../../api/relationships', () => ({ listRelationships: async () => [], listBlocks: async () => [] }))
vi.mock('../../api/characters', () => ({ getCharacter: async () => ({}) }))

import '../../i18n'
import CharacterProfile from '../CharacterProfile'
import Tasks from '../Tasks'
import FactionDetail from '../FactionDetail'
import FieldDesk from '../FieldDesk'

afterEach(() => {
  cleanup()
  signup.msg = null
})

const SURFACES: [string, () => ReactElement][] = [
  ['Tasks', () => <Tasks />],
  ['FactionDetail', () => <FactionDetail slug="everymen" />],
  ['CharacterProfile', () => <CharacterProfile />],
  ['FieldDesk', () => <FieldDesk />],
]

describe('a failed sign-up is announced', () => {
  it.each(SURFACES)('%s wraps signupMsg in role=alert', (_n, page) => {
    signup.msg = MSG
    render(<MemoryRouter>{page()}</MemoryRouter>)
    expect(screen.getByRole('alert').textContent).toContain(MSG)
  })
})
