import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom'
import { BrandMark } from './components/BrandMark'
import { Dock } from './components/Dock'
import { LanguageSheet } from './components/LanguageSheet'
import { UI_LANGUAGES } from './i18n'
import { ApiError, getMe, giveConsent, saveLanguage } from './lib/api'
import { AuthProvider, useAuth } from './lib/auth'
import { chooseLanguage } from './lib/language'
import { CheckPage, SharedCheck } from './screens/CheckPage'
import { History } from './screens/History'
import { Home } from './screens/Home'
import { LatestCheck } from './screens/LatestCheck'
import { PublicResult } from './screens/PublicResult'
import { Trending } from './screens/Trending'
import { Welcome } from './screens/Welcome'

function Header({ onLanguage }: { onLanguage: () => void }) {
  const { t, i18n } = useTranslation()
  const current = UI_LANGUAGES.find((l) => l.code === i18n.resolvedLanguage) ?? UI_LANGUAGES[0]
  return (
    <header className="topbar">
      <Link to="/" className="brand">
        <BrandMark />
        {t('app.name')}
      </Link>
      <button type="button" className="lang-btn" onClick={onLanguage} aria-label={`${t('nav.language')}: ${current.name}`}>
        {current.code.toUpperCase()} <span aria-hidden="true">▾</span>
      </button>
    </header>
  )
}

function Gate() {
  const { user, loading, signIn } = useAuth()
  const { i18n, t } = useTranslation()
  const location = useLocation()
  const [consented, setConsented] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sheet, setSheet] = useState(false)
  const choose = (code: string) => chooseLanguage(code, user, Boolean(consented))

  useEffect(() => {
    setConsented(null)
    if (!user) return
    getMe(user)
      .then((me) => {
        setConsented(Boolean(me.consent_at))
        // The choice made on this device before signing in wins; the profile keeps it for notifications.
        const lng = i18n.resolvedLanguage
        if (me.consent_at && lng && me.ui_language !== lng) {
          saveLanguage(user, lng).catch((e: unknown) => console.error('PUT /v1/me/language failed', e))
        }
      })
      .catch((e: unknown) => {
        console.error('GET /v1/me failed', e)
        setConsented(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

  const languageSheet = <LanguageSheet open={sheet} onClose={() => setSheet(false)} onChoose={choose} />

  if (location.pathname.startsWith('/r/')) {
    return (
      <>
        <Header onLanguage={() => setSheet(true)} />
        <Routes>
          <Route path="/r/:verdictId" element={<PublicResult />} />
        </Routes>
        {languageSheet}
      </>
    )
  }
  if (loading || (user && consented === null)) return <main className="screen center muted">…</main>
  if (!user || !consented) {
    return (
      <Welcome
        signedIn={Boolean(user)}
        busy={busy}
        error={error}
        onLanguage={choose}
        onSignIn={() => {
          setBusy(true)
          setError(null)
          signIn().finally(() => setBusy(false))
        }}
        onAgree={() => {
          if (!user) return
          setBusy(true)
          setError(null)
          giveConsent(user, i18n.resolvedLanguage ?? 'en')
            .then(() => setConsented(true))
            .catch((e: unknown) => {
              console.error('POST /v1/me/consent failed', e)
              const code = e instanceof ApiError ? e.code : 'generic'
              setError(t(`errors.${code}`, { defaultValue: t('errors.generic') }))
            })
            .finally(() => setBusy(false))
        }}
      />
    )
  }
  return (
    <>
      <Header onLanguage={() => setSheet(true)} />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/check" element={<SharedCheck />} />
        <Route path="/check/:checkId" element={<CheckPage />} />
        <Route path="/checks" element={<LatestCheck />} />
        <Route path="/trending" element={<Trending />} />
        <Route path="/history" element={<History />} />
        <Route path="*" element={<Home />} />
      </Routes>
      <Dock onLanguage={() => setSheet(true)} />
      {languageSheet}
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Gate />
      </BrowserRouter>
    </AuthProvider>
  )
}
