/** Dates and language names in the reader's UI language, with the browser's own translations. */

export function languageName(code: string | null | undefined, uiLanguage: string): string {
  if (!code) return ''
  try {
    return new Intl.DisplayNames([uiLanguage], { type: 'language' }).of(code.split('-')[0] ?? code) ?? code
  } catch {
    return code
  }
}

export function timeAgo(iso: string, uiLanguage: string, now = Date.now()): string {
  const s = Math.round((new Date(iso).getTime() - now) / 1000)
  const rtf = new Intl.RelativeTimeFormat(uiLanguage, { numeric: 'auto' })
  if (Math.abs(s) < 3600) return rtf.format(Math.round(s / 60), 'minute')
  if (Math.abs(s) < 86400) return rtf.format(Math.round(s / 3600), 'hour')
  if (Math.abs(s) < 7 * 86400) return rtf.format(Math.round(s / 86400), 'day')
  return new Date(iso).toLocaleDateString(uiLanguage, { day: 'numeric', month: 'short' })
}
