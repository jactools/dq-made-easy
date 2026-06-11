/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import { AuthContext } from './AuthContext'
import { AsyncRequestTrackerProvider } from './AsyncRequestTrackerContext'
import { PerformanceMonitoringProvider } from './PerformanceMonitoringContext'
import { SettingsContext } from './SettingsContext'

afterEach(() => {
  cleanup()
})

describe('AsyncRequestTrackerProvider', () => {
  it('mounts without requiring undeclared API helper bindings', () => {
    render(
      <PerformanceMonitoringProvider>
        <SettingsContext.Provider value={{ applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1' } } as any}>
          <AuthContext.Provider value={{ isAuthenticated: false, currentWorkspaceId: null, user: null } as any}>
            <AsyncRequestTrackerProvider>
              <div data-testid="tracker-child" />
            </AsyncRequestTrackerProvider>
          </AuthContext.Provider>
        </SettingsContext.Provider>
      </PerformanceMonitoringProvider>,
    )

    expect(screen.getByTestId('tracker-child')).toBeTruthy()
  })
})