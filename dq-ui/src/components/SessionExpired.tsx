import React, { useCallback } from 'react'
import { Button } from './Button'

type SessionExpiredProps = {
  onOpenLogin: () => void
}

export const SessionExpired: React.FC<SessionExpiredProps> = ({
  onOpenLogin,
}) => {
  const openLogin = useCallback(() => {
    // Remove the session-expired flag to avoid repeated redirects.
    try { sessionStorage.removeItem('dq-session-expired') } catch {}

    onOpenLogin()
  }, [onOpenLogin])

  return (
    <div style={{ padding: 24, textAlign: 'center' }}>
      <h2>Signed out after session timeout</h2>
      <p>You were logged out because your session timed out due to inactivity. Please sign in again.</p>
      <Button onClick={openLogin}>Open Login</Button>
    </div>
  )
}

export default SessionExpired
