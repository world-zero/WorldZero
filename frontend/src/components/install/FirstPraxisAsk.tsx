import { lazy, Suspense } from 'react'
import { useFormFactor } from '../../hooks/useFormFactor'
import PushAsk from '../push/PushAsk'

const InstallSheet = lazy(() => import('./InstallSheet'))

/** Under the first praxis: the wisp's install sheet on a phone, the push ask on desktop (#4052). */
export default function FirstPraxisAsk({ praxisId }: { readonly praxisId: number }) {
  if (useFormFactor() !== 'mobile') return <PushAsk praxisId={praxisId} />
  return (
    <Suspense fallback={null}>
      <InstallSheet praxisId={praxisId} />
    </Suspense>
  )
}
