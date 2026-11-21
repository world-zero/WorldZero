import { apiGet, apiPut } from '../../api/client'
import { saveBody } from '../../pages/settings/notificationPrefs'
import { subscribePush } from '../../utils/pushSubscribe'

// A yes turns `vote_on_mine` push on against its default: the ask's copy promised exactly these rows.
const ASKED_ROWS = ['vote_on_mine', 'comment_on_mine', 'comment_mention']

export async function turnOnAskedPush(vapidKey: string): Promise<Awaited<ReturnType<typeof subscribePush>>> {
  const result = await subscribePush(vapidKey)
  if (result === 'ok') {
    const { data } = await apiGet('/me/notification-prefs')
    const next = { ...data.events }
    for (const key of ASKED_ROWS) if (next[key]) next[key] = { ...next[key], by_push: true }
    await apiPut('/me/notification-prefs', { body: saveBody(next) })
  }
  return result
}
