/** Two-letter tile text from a publisher name or domain. Not the publisher's logo, which needs permission. */
export function monogram(name: string): string {
  // A bare domain ("thequint.com") is one name: drop "www." and the ending, or it reads "TC".
  const bare = /^[\w.-]+\.[a-z]{2,}$/i.test(name.trim()) ? name.trim().replace(/^www\./i, '').replace(/\.[^.]+$/, '') : name
  const words = bare.split(/[\s.\-_]+/).filter(Boolean)
  const first = words[0] ?? '?'
  return (words.length > 1 ? words[0]![0]! + words[1]![0]! : first.slice(0, 2)).toUpperCase()
}
