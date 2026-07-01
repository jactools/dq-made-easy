import React, { createContext, useContext, useState, useLayoutEffect, ReactNode } from 'react'

type ThemeMode = 'light' | 'dark' | 'system'

interface ThemeContextType {
  mode: ThemeMode
  setMode: (mode: ThemeMode) => void
  effectiveMode: 'light' | 'dark'
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

const THEME_STORAGE_KEY = 'dq-theme-preference'

const normalizeThemeMode = (value: string | null): ThemeMode => {
  if (value === 'light' || value === 'dark' || value === 'system') {
    return value
  }
  if (value === 'auto') {
    return 'system'
  }
  return 'system'
}

const applyThemeAttributes = (effective: 'light' | 'dark') => {
  document.documentElement.setAttribute('data-theme', effective)
  document.documentElement.setAttribute('data-app-theme', effective)
  document.documentElement.classList.toggle('dark', effective === 'dark')
}

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    // Load saved preference from localStorage, default to 'system'
    return normalizeThemeMode(localStorage.getItem(THEME_STORAGE_KEY))
  })

  const [effectiveMode, setEffectiveMode] = useState<'light' | 'dark'>('light')

  // Detect system preference
  const getSystemPreference = (): 'light' | 'dark' => {
    if (typeof window !== 'undefined') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return 'light'
  }

  // Update effective mode based on selected mode and system preference
  useLayoutEffect(() => {
    const updateEffectiveMode = () => {
      const effective = mode === 'system' ? getSystemPreference() : mode
      setEffectiveMode(effective)
      applyThemeAttributes(effective)
    }

    updateEffectiveMode()

    // Listen for system theme changes if "system" is selected
    if (mode === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      const handleChange = () => updateEffectiveMode()
      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }
  }, [mode])

  const setMode = (newMode: ThemeMode) => {
    setModeState(newMode)
    localStorage.setItem(THEME_STORAGE_KEY, newMode === 'system' ? 'auto' : newMode)
  }

  return (
    <ThemeContext.Provider value={{ mode, setMode, effectiveMode }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = (): ThemeContextType => {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
