/*
 * useTheme.ts
 * Dark/light theme state for the whole app, persisted to localStorage and
 * applied via a `data-theme` attribute on <html> — index.css defines the
 * two token sets scoped to `:root` (dark, the default) and
 * `:root[data-theme='light']`. This is deliberately a per-browser UI
 * preference, not something the backend knows about or the API exposes.
 */
import { useCallback, useEffect, useState } from 'react'

type Theme = 'dark' | 'light'

const STORAGE_KEY = 'fcc-dashboard-theme'

function readStoredTheme(): Theme {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    // Private browsing / storage disabled — fall back to the default
    // rather than letting a storage access error crash the whole app.
    return 'dark'
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme)

  useEffect(() => {
    if (theme === 'light') {
      document.documentElement.setAttribute('data-theme', 'light')
    } else {
      document.documentElement.removeAttribute('data-theme')
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // Same fallback as above — a failed write just means the choice
      // won't persist across reloads, not a reason to throw.
    }
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'))
  }, [])

  return { theme, toggleTheme }
}
