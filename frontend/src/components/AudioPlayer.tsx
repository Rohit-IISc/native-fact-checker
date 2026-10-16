import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

function clock(s: number): string {
  if (!Number.isFinite(s) || s < 0) return '–:––'
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`
}

/** Play button, progress and time. The duration loads with the file's metadata, so it shows before the
 *  first tap (the old player used preload="none" and showed 0:00 / 0:00 until played). */
export function AudioPlayer({ src, lang }: { src: string; lang?: string }) {
  const { t } = useTranslation()
  const ref = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(Number.NaN)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setPlaying(false)
    setTime(0)
    setDuration(Number.NaN)
    setFailed(false)
  }, [src])

  const toggle = () => {
    const a = ref.current
    if (!a) return
    if (a.paused) a.play().catch(() => setFailed(true))
    else a.pause()
  }

  const seek = (value: number) => {
    const a = ref.current
    if (a && Number.isFinite(a.duration)) a.currentTime = value
  }

  const known = Number.isFinite(duration) && duration > 0
  return (
    <div className="player" lang={lang}>
      <audio
        ref={ref}
        src={src}
        preload="metadata"
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onDurationChange={(e) => setDuration(e.currentTarget.duration)}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onError={() => setFailed(true)}
      />
      <button type="button" className="play" onClick={toggle} aria-label={playing ? t('result.pause') : t('result.listen')} disabled={failed}>
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          {playing ? <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" /> : <path d="M8 5l11 7-11 7z" fill="currentColor" />}
        </svg>
      </button>
      <input
        type="range"
        min={0}
        max={known ? duration : 1}
        step={0.1}
        value={known ? Math.min(time, duration) : 0}
        onChange={(e) => seek(Number(e.target.value))}
        aria-label={t('result.audioPosition')}
        disabled={!known}
        style={{ ['--p' as string]: `${known ? (Math.min(time, duration) / duration) * 100 : 0}%` }}
      />
      <span className="time">
        {failed ? t('result.audioFailed') : `${clock(time)} / ${known ? clock(duration) : '–:––'}`}
      </span>
    </div>
  )
}
