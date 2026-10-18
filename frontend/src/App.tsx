import { lazy, Suspense, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom'
import { BrandMark } from './components/BrandMark'
import { Dock } from './components/Dock'
import { LanguageSheet } from './components/LanguageSheet'
import { UI_LANGUAGES } from './i18n'
import { ApiError, getMe, giveConsent, saveLanguage } from './lib/api'
import { AuthProvider, useAuth } from './lib/auth'
import { chooseLanguage } from './lib/language'
import { Home } from './screens/Home'
import { Welcome } from './screens/Welcome'

// Screens other than the landing page and Home load on first use (smaller first download).
const CheckPage = lazy(() => import('./screens/CheckPage').then((m) => ({ default: m.CheckPage })))
const SharedCheck = lazy(() => import('./screens/CheckPage').then((m) => ({ default: m.SharedCheck })))
const History = lazy(() => import('./screens/History').then((m) => ({ default: m.History })))
const LatestCheck = lazy(() => import('./screens/LatestCheck').then((m) => ({ default: m.LatestCheck })))
const Legal = lazy(() => import('./screens/Legal').then((m) => ({ default: m.Legal })))
const PublicResult = lazy(() => import('./screens/PublicResult').then((m) => ({ default: m.PublicResult })))
const Example = lazy(() => import('./screens/Example').then((m) => ({ default: m.Example })))
const Trending = lazy(() => import('./screens/Trending').then((m) => ({ default: m.Trending })))
const screenFallback = <main className="screen center muted">…</main>

/** A new screen opens at its top (the browser keeps the old scroll position on client-side navigation). */
function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

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
  const [sheet, setSheet] = useState<'language' | 'settings' | null>(null)
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

  const languageSheet = <LanguageSheet mode={sheet} onClose={() => setSheet(null)} onChoose={choose} />

  // Public pages: no sign-in needed.
  if (location.pathname.startsWith('/r/') || location.pathname === '/privacy' || location.pathname === '/terms') {
    return (
      <>
        <Header onLanguage={() => setSheet('language')} />
        <Suspense fallback={screenFallback}>
        <Routes>
          <Route path="/r/:verdictId" element={<PublicResult />} />
          <Route path="/privacy" element={<Legal kind="privacy" />} />
          <Route path="/terms" element={<Legal kind="terms" />} />
        </Routes>
        </Suspense>
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
      <Header onLanguage={() => setSheet('language')} />
      <Suspense fallback={screenFallback}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/check" element={<SharedCheck />} />
        <Route path="/check/:checkId" element={<CheckPage />} />
        <Route path="/checks" element={<LatestCheck />} />
        <Route path="/trending" element={<Trending />} />
        <Route path="/example/:key" element={<Example />} />
        <Route path="/history" element={<History />} />
        <Route path="*" element={<Home />} />
      </Routes>
      </Suspense>
      <Dock onSettings={() => setSheet('settings')} />
      {languageSheet}
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ScrollToTop />
        <Gate />
      </BrowserRouter>
    </AuthProvider>
  )
}
