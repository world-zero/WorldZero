import { listPraxes } from '../api/praxis'

/** Is this the player's one and only submitted praxis? PushAsk (#3704) and the install sheet (#4052) both ask this. */
export async function isFirstPraxis(characterId: number, praxisId: number): Promise<boolean> {
  const mine = await listPraxes({ member_id: characterId, status: 'submitted', era_scope: 'all_eras', limit: 2 })
  return mine.length === 1 && mine[0].id === praxisId
}
