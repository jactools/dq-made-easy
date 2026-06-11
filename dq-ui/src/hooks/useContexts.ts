import { useContext } from 'react'
import { RuleContext } from '../contexts/RuleContext'
import { AuthContext } from '../contexts/AuthContext'
import { SettingsContext, SettingsContextType } from '../contexts/SettingsContext'
import { NotificationContext } from '../contexts/NotificationContext'

export const useRules = () => {
  const context = useContext(RuleContext)
  if (!context) {
    throw new Error('useRules must be used within RuleProvider')
  }
  return context
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}

export const useSettings = (): SettingsContextType => {
  const context = useContext(SettingsContext)
  if (!context) {
    throw new Error('useSettings must be used within SettingsProvider')
  }
  return context
}

export const useSettingsOptional = (): SettingsContextType | null => useContext(SettingsContext)

export const useNotifications = () => {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotifications must be used within NotificationProvider')
  }
  return context
}
