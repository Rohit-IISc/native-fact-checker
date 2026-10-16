const PATHS = {
  text: 'M4 6h16M4 12h16M4 18h10',
  image: 'M3 6a2 2 0 012-2h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2zM9 10a1.5 1.5 0 100-.01M21 16l-5-5-8 8',
  video: 'M3 8a2 2 0 012-2h9a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2zM16 10l5-3v10l-5-3',
  mic: 'M9 6a3 3 0 016 0v5a3 3 0 01-6 0zM5 11a7 7 0 0014 0M12 18v3',
  link: 'M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1',
  home: 'M3 11l9-8 9 8v10h-6v-6H9v6H3z',
  clock: 'M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 2',
} as const

export type IconName = keyof typeof PATHS

/** Small stroke icon. Decorative: the label next to it carries the meaning. */
export function Icon({ name }: { name: IconName }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  )
}
