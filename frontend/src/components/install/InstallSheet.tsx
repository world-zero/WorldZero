import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/AuthContext'
import { isFirstPraxis } from '../../utils/firstPraxis'
import { firstAskDue, installPlatform, markVisit, patchAsk, readAsk } from '../../utils/installAsk'
import { isStandalone } from '../../utils/installPrompt'
import InstallFlow from './InstallFlow'

/** On a phone this replaces PushAsk under the player's first praxis (#4052). The caller has already checked the form factor. */
export default function InstallSheet({ praxisId }: { readonly praxisId: number }) {
  const characterId = useAuth().user?.character?.id
  const [platform, setPlatform] = useState<ReturnType<typeof installPlatform>>(null)

  useEffect(() => {
    const where = installPlatform()
    if (characterId == null || !firstAskDue(readAsk(), { phone: true, standalone: isStandalone(), platform: where })) return
    let live = true
    isFirstPraxis(characterId, praxisId)
      .then((first) => {
        if (!live || !first) return
        if (readAsk().first === undefined) patchAsk({ first: Date.now() })
        markVisit()
        setPlatform(where)
      })
      .catch(() => {})
    return () => {
      live = false
    }
  }, [characterId, praxisId])

  if (!platform) return null
  return (
    <InstallFlow
      platform={platform}
      onAnswered={() => patchAsk({ firstDone: true })}
      onClose={() => setPlatform(null)}
    />
  )
}
