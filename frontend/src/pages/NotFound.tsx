import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

/** Last route in `PlayerRoutes`: a path nothing else claims. */
export default function NotFound() {
  const { t } = useTranslation('common')
  useDocumentTitle(t('states.pageNotFound'))
  return (
    <div className="py-8 font-body text-muted">
      {t('states.pageNotFound')}{' '}
      <Link to="/" className="underline">
        {t('states.backHome')}
      </Link>
    </div>
  )
}
