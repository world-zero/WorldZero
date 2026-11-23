// @vitest-environment jsdom
/** The own-profile edit link reaches every skin through `identityActions`. Seam: CharacterProfile's slot prop. */
import { render, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const signup = vi.hoisted(() => ({ msg: null as string | null, viewerId: 1 }))

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
  useAuth: () => ({ user: { character: { id: signup.viewerId, faction_slug: 'everymen' } }, applyUser: () => {} }),
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
vi.mock('../characterProfile/FactionProfileBody', () => ({
  default: ({ identityActions }: { identityActions: unknown }) => <>{identityActions}</>,
}))
vi.mock('../../components/backdrop/BackdropContext', () => ({ useFactionBackdrop: () => {} }))
vi.mock('../../api/relationships', () => ({ listRelationships: async () => [], listBlocks: async () => [] }))
vi.mock('../../api/characters', () => ({ getCharacter: async () => ({}) }))

import '../../i18n'
import CharacterProfile from '../CharacterProfile'

afterEach(cleanup)

describe('own-profile edit link', () => {
  it('shows for the viewer\'s own character, pointing at its edit page', () => {
    signup.viewerId = 1
    const { container } = render(<MemoryRouter><CharacterProfile /></MemoryRouter>)
    expect(container.querySelector('a[href="/characters/1/edit"]')).not.toBeNull()
  })
  it('is absent on someone else\'s profile', () => {
    signup.viewerId = 2
    const { container } = render(<MemoryRouter><CharacterProfile /></MemoryRouter>)
    expect(container.querySelector('a[href$="/edit"]')).toBeNull()
  })
})
