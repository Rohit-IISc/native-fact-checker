import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { UI_LANGUAGES } from '../i18n'
import { useAuth } from '../lib/auth'
import { Icon } from './Icon'

/** Bottom sheet opened from the header's language button and the dock. Sign out lives here too. */
export function LanguageSheet({ open, onClose, onChoose }: { open: boolean; onClose: () => void; onChoose: (code: string) => void }) {
  const { t, i18n } = useTranslation()
  const { user, signOut } = useAuth()
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

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
        <h2 id="sheet-title">{t('nav.chooseLanguage')}</h2>
        <button type="button" className="icon-btn" aria-label={t('nav.close')} onClick={onClose}>
          <Icon name="close" />
        </button>
      </div>
      <ul className="lang-list">
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
    </dialog>
  )
}
