import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'
import en from './en.json'
import hi from './hi.json'
import id from './id.json'
import kn from './kn.json'
import ta from './ta.json'

export const UI_LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'hi', name: 'हिन्दी' },
  { code: 'ta', name: 'தமிழ்' },
  { code: 'kn', name: 'ಕನ್ನಡ' },
  { code: 'id', name: 'Bahasa Indonesia' },
] as const

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, hi: { translation: hi }, ta: { translation: ta }, kn: { translation: kn }, id: { translation: id } },
    fallbackLng: 'en',
    supportedLngs: UI_LANGUAGES.map((l) => l.code),
    nonExplicitSupportedLngs: true,
    load: 'languageOnly',
    interpolation: { escapeValue: false },
    detection: { order: ['localStorage', 'navigator'], caches: ['localStorage'] },
  })

i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng
})

export default i18n

/** i18n language for content in `bcp47` (e.g. "hi-IN" -> "hi"); unsupported languages fall back to English. */
export function contentLng(bcp47: string | null | undefined): string | undefined {
  if (!bcp47) return undefined
  const base = (bcp47.split('-')[0] ?? '').toLowerCase()
  return UI_LANGUAGES.some((l) => l.code === base) ? base : 'en'
}
