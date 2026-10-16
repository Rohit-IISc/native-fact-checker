import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom'
import { BrandMark } from './components/BrandMark'
import { Dock } from './components/Dock'
import { UI_LANGUAGES } from './i18n'
import { ApiError, getMe, giveConsent } from './lib/api'
import { AuthProvider, useAuth } from './lib/auth'
import { CheckPage, SharedCheck } from './screens/CheckPage'
import { History } from './screens/History'
import { Home } from './screens/Home'
import { PublicResult } from './screens/PublicResult'
import { Welcome } from './screens/Welcome'

function LanguagePicker() {
  const { t, i18n } = useTranslation()
  return (
    <select
      aria-label={t('nav.language')}
      value={i18n.resolvedLanguage}
      onChange={(e) => void i18n.changeLanguage(e.target.value)}
    >
      {UI_LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.name}
        </option>
      ))}
    </select>
  )
}

function Header() {
  const { t } = useTranslation()
  const { user, signOut } = useAuth()
  return (
    <header className="topbar">
      <Link to="/" className="brand">
        <BrandMark />
        {t('app.name')}
      </Link>
      <nav>
        <LanguagePicker />
        {user && (
          <button className="link" onClick={() => void signOut()}>
            {t('nav.signOut')}
          </button>
        )}
      </nav>
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

  useEffect(() => {
    setConsented(null)
    if (!user) return
    getMe(user)
      .then((me) => setConsented(Boolean(me.consent_at)))
      .catch((e: unknown) => {
        console.error('GET /v1/me failed', e)
        setConsented(false)
      })
  }, [user])

  if (location.pathname.startsWith('/r/')) {
    return (
      <Routes>
        <Route path="/r/:verdictId" element={<PublicResult />} />
      </Routes>
    )
  }
  if (loading || (user && consented === null)) return <main className="screen center muted">…</main>
  if (!user || !consented) {
    return (
      <Welcome
        signedIn={Boolean(user)}
        busy={busy}
        error={error}
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
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/check" element={<SharedCheck />} />
        <Route path="/check/:checkId" element={<CheckPage />} />
        <Route path="/history" element={<History />} />
        <Route path="*" element={<Home />} />
      </Routes>
      <Dock />
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Header />
        <Gate />
      </BrowserRouter>
    </AuthProvider>
  )
}
