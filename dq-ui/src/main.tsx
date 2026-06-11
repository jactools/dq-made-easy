import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ThemeProvider } from './contexts/ThemeContext'
import { PerformanceMonitoringProvider } from './contexts/PerformanceMonitoringContext'
import { initTelemetry } from './telemetry'
import './statusBadges.css'
import './themes.css'
import './styles/appPatterns.css'
import './App.css'

initTelemetry()

const root = createRoot(document.getElementById('root')!)
root.render(
  <React.StrictMode>
    <PerformanceMonitoringProvider>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </PerformanceMonitoringProvider>
  </React.StrictMode>
)

