import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { UI_LANGUAGES } from '../i18n'
import { deleteAccount } from '../lib/api'
import { useAuth } from '../lib/auth'
import { LegalLinks } from './LegalLinks'
import { Icon } from './Icon'

/** Bottom sheet in two modes. "language" (the header's language button): only the language list.
 *  "settings" (the dock's Settings item): display language as a dropdown, then the account (sign out,
 *  delete) and the privacy and terms pages. */
export function LanguageSheet({ mode, onClose, onChoose }: {
  mode: 'language' | 'settings' | null
  onClose: () => void
  onChoose: (code: string) => void
}) {
  const open = mode !== null
  const { t, i18n } = useTranslation()
  const { user, signOut } = useAuth()
  const ref = useRef<HTMLDialogElement>(null)
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
    if (!open) {
      setConfirming(false)
      setFailed(false)
    }
  }, [open])

  const remove = () => {
    if (!user) return
    setDeleting(true)
    setFailed(false)
    deleteAccount(user)
      .then(() => {
        onClose()
        void signOut()
      })
      .catch((e: unknown) => {
        console.error('DELETE /v1/me failed', e)
        setFailed(true)
      })
      .finally(() => setDeleting(false))
  }

  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-labelledby="sheet-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose() // a tap on the backdrop
      }}
    >
      <div className="sheet-head">
        <h2 id="sheet-title">{mode === 'settings' ? t('nav.settings') : t('nav.chooseLanguage')}</h2>
        <button type="button" className="icon-btn" aria-label={t('nav.close')} onClick={onClose}>
          <Icon name="close" />
        </button>
      </div>
      {mode === 'language' && (
        <>
          <ul className="lang-list" aria-label={t('nav.chooseLanguage')}>
            {UI_LANGUAGES.map((l) => {
              const on = i18n.resolvedLanguage === l.code
              return (
                <li key={l.code}>
                  <button
                    type="button"
                    lang={l.code}
                    className={on ? 'on' : undefined}
                    aria-pressed={on}
                    onClick={() => {
                      onChoose(l.code)
                      onClose()
                    }}
                  >
                    <span>{l.name}</span>
                    {on && <Icon name="check" />}
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
      {mode === 'settings' && (
        <>
          <h3>
            <label htmlFor="ui-language">{t('nav.displayLanguage')}</label>
          </h3>
          <select
            id="ui-language"
            className="lang-select"
            value={i18n.resolvedLanguage}
            onChange={(e) => onChoose(e.target.value)}
          >
            {UI_LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} lang={l.code}>
                {l.name}
              </option>
            ))}
          </select>
          {user && <h3>{t('nav.account')}</h3>}
          {user && (
            <button
              type="button"
              className="signout"
              onClick={() => {
                onClose()
                void signOut()
              }}
            >
              <Icon name="logout" />
              {t('nav.signOut')}
            </button>
          )}
          {user && !confirming && (
            <button type="button" className="link danger" onClick={() => setConfirming(true)}>
              {t('account.delete')}
            </button>
          )}
          {user && confirming && (
            <div className="confirm" role="alert">
              <p>{t('account.confirm')}</p>
              {failed && <p className="error">{t('errors.generic')}</p>}
              <div className="row">
                <button type="button" className="secondary" onClick={() => setConfirming(false)} disabled={deleting}>
                  {t('account.keep')}
                </button>
                <button type="button" className="danger-btn" onClick={remove} disabled={deleting}>
                  {t('account.deleteNow')}
                </button>
              </div>
            </div>
          )}
          <LegalLinks />
        </>
      )}
    </dialog>
  )
}
