import { useTranslation } from 'react-i18next'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import PageTitle from '../components/ui/PageTitle'

export default function About() {
  const { t } = useTranslation('common')
  useDocumentTitle(t('about.title'))
  return (
    <div className="py-8 max-w-2xl">
      <PageTitle title={t('about.title')} />

      <div className="card p-6 mb-6">
        <p className="font-body text-base leading-relaxed mb-4">
          {t('about.intro1')}
        </p>
        <p className="font-body text-base leading-relaxed">
          {t('about.intro2')}
        </p>
      </div>
    </div>
  )
}
