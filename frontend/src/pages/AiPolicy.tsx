import { useTranslation } from 'react-i18next'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import PageTitle from '../components/ui/PageTitle'

export default function AiPolicy() {
  const { t } = useTranslation('common')
  useDocumentTitle(t('ai.title'))
  return (
    <div className="py-8 max-w-2xl">
      <PageTitle title={t('ai.title')} />

      <div className="card p-6 space-y-5 font-body text-base leading-relaxed">
        <h2 className="font-display text-2xl font-bold">{t('ai.builtTitle')}</h2>
        <p className="whitespace-pre-line">{t('ai.built')}</p>
        <h2 className="font-display text-2xl font-bold">{t('ai.praxisTitle')}</h2>
        <p className="whitespace-pre-line">{t('ai.praxis')}</p>
      </div>
    </div>
  )
}
