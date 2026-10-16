import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router-dom'
import { Icon } from './Icon'

/** Bottom navigation for signed-in screens. Thumb-reach on a phone, one tap to each main screen. */
export function Dock() {
  const { t } = useTranslation()
  return (
    <nav className="dock" aria-label={t('nav.main')}>
      <NavLink to="/" end>
        <Icon name="home" />
        {t('nav.home')}
      </NavLink>
      <NavLink to="/history">
        <Icon name="clock" />
        {t('nav.history')}
      </NavLink>
    </nav>
  )
}
