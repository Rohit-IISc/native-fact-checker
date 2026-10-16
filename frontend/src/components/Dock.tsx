import { useTranslation } from 'react-i18next'
import { NavLink, useLocation } from 'react-router-dom'
import { Icon } from './Icon'

/** Bottom navigation for signed-in screens. Thumb-reach on a phone, one tap to each main screen. */
export function Dock({ onSettings }: { onSettings: () => void }) {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const onCheck = pathname === '/checks' || pathname.startsWith('/check/') || pathname === '/check'
  return (
    <nav className="dock" aria-label={t('nav.main')}>
      <NavLink to="/" end>
        <Icon name="home" />
        {t('nav.home')}
      </NavLink>
      <NavLink to="/checks" className={onCheck ? 'active' : undefined} aria-current={onCheck ? 'page' : undefined}>
        <Icon name="shield" />
        {t('nav.checks')}
      </NavLink>
      <NavLink to="/trending">
        <Icon name="flame" />
        {t('nav.trending')}
      </NavLink>
      <NavLink to="/history">
        <Icon name="clock" />
        {t('nav.history')}
      </NavLink>
      <button type="button" onClick={onSettings} aria-haspopup="dialog">
        <Icon name="gear" />
        {t('nav.settings')}
      </button>
    </nav>
  )
}
