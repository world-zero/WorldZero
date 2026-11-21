import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { getActivityFeed } from '../../api/activityFeed'
import { useAuth } from '../../auth/AuthContext'
import { patchAsk, readAsk, installPlatform, reAskDue, reAskPossible, welcomeDue } from '../../utils/installAsk'
import { isStandalone } from '../../utils/installPrompt'
import { deviceSubscribed, pushBlock } from '../../utils/pushSubscribe'
import Housewarming from './Housewarming'
import InstallFlow from './InstallFlow'

/** Home on a phone (#4052): the housewarming on the first home-screen open, or the one re-ask after a rating. */
export default function HomeInstallAsks() {
  const name = useAuth().user?.character?.display_name?.trim() ?? ''
  const [vapidKey, setVapidKey] = useState<string | null>(null)
  const [reask, setReask] = useState<ReturnType<typeof installPlatform>>(null)

  useEffect(() => {
    const env = { phone: true, standalone: isStandalone(), platform: installPlatform() }
    const s = readAsk()
    let live = true
    const run = async () => {
      if (welcomeDue(s, env)) {
        const { data } = await apiGet('/me/notification-prefs')
        const key = data.vapid_public_key ?? null
        if (key && pushBlock(key) === 'ok' && !(await deviceSubscribed()) && live) setVapidKey(key)
      } else if (reAskPossible(s, env)) {
        const rated = s.second === undefined ? (await getActivityFeed({ types: ['vote_on_mine'], limit: 1 })).items[0] : undefined
        const at = rated ? Date.parse(rated.timestamp) : NaN
        if (!live || !reAskDue(readAsk(), env, Number.isNaN(at) ? null : at)) return
        if (s.second === undefined) patchAsk({ second: Date.now() })
        setReask(env.platform)
      }
    }
    run().catch(() => {})
    return () => {
      live = false
    }
  }, [])

  if (vapidKey)
    return (
      <Housewarming
        vapidKey={vapidKey}
        name={name}
        platform={/Android/.test(navigator.userAgent) ? 'android' : 'iphone'}
        onAnswered={() => patchAsk({ welcomed: true })}
        onClose={() => setVapidKey(null)}
      />
    )
  if (reask)
    return (
      <InstallFlow
        reask
        platform={reask}
        onAnswered={() => patchAsk({ secondDone: true })}
        onClose={() => setReask(null)}
      />
    )
  return null
}
