import i18n from '../i18n'
import { saveLanguage } from './api'
import type { AppUser } from './auth'

/** Switch every screen at once. i18next keeps the choice in localStorage; a signed-in user's profile gets it
 *  too, so notifications come in the same language. A failed save is not shown: the screen already changed. */
export function chooseLanguage(code: string, user: AppUser | null, consented: boolean) {
  void i18n.changeLanguage(code)
  if (user && consented) {
    saveLanguage(user, code).catch((e: unknown) => console.error('PUT /v1/me/language failed', e))
  }
}
