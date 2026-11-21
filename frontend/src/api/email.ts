import { apiPost } from './client'

/** Turn off email for the one event that sent the mail; the signed token is the credential (#2164). Idempotent. */
export async function unsubscribeEmail(token: string): Promise<string> {
  const { data } = await apiPost('/email/unsubscribe', { params: { query: { token } } })
  return data.event
}

/** "Turn them all off": every row's email, not only the one that sent this. */
export async function unsubscribeAllEmail(token: string): Promise<void> {
  await apiPost('/email/unsubscribe-all', { params: { query: { token } } })
}
