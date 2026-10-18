import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { ResultView } from '../components/ResultView'
import { getExample } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { CheckDoc } from '../lib/types'

/** /example/:key: a seeded demo share answered from the cache. No check is created and no quota is used. */
export function Example() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { key } = useParams()
  const [doc, setDoc] = useState<CheckDoc | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!user || !key) return
    getExample(user, key).then(setDoc).catch(() => setFailed(true))
  }, [user, key])

  return (
    <main className="screen">
      {key && <p className="example-tag">{t('examples.tag', { name: t(`examples.items.${key}`) })}</p>}
      {failed && <p className="card error">{t('errors.generic')}</p>}
      {!doc && !failed && <p className="muted">…</p>}
      {doc?.result && <ResultView result={doc.result} />}
      <Link className="button secondary" to="/">
        {t('examples.back')}
      </Link>
    </main>
  )
}
