import { apiGet } from './client'
import type { CharacterOut } from './auth'

export async function getLeaderboard(params?: { limit?: number; offset?: number; era?: number }): Promise<CharacterOut[]> {
  const { data } = await apiGet('/leaderboard', { params: { query: params } })
  return data
}

export async function getLeaderboardEra(eraId: number): Promise<{ id: number; name: string }> {
  const { data } = await apiGet('/leaderboard/era/{era_id}', { params: { path: { era_id: eraId } } })
  return data
}
