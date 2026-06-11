import React from 'react'
import { useTheme } from '../contexts/ThemeContext'
import { AppSelect } from './app-primitives'

export const ThemeSwitcher: React.FC = () => {
  const { mode, setMode, effectiveMode } = useTheme()

  return (
    <div className="theme-switcher">
      <AppSelect
        id="theme-select"
        label="Theme:"
        value={mode}
        onChange={(value) => setMode(value as 'light' | 'dark' | 'system')}
        options={[
          { value: 'light', label: 'Light' },
          { value: 'dark', label: 'Dark' },
          { value: 'system', label: 'System' },
        ]}
      />
      <span className="theme-status">(Effective: {effectiveMode})</span>
    </div>
  )
}
