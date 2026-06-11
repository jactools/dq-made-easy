import React from 'react'

export const Welcome: React.FC<{ userName?: string }> = ({ userName = 'User' }) => {
  return (
    <section className="welcome-section">
      <h2>Welcome back, {userName}! 👋</h2>
      <p>Here's what's happening with your data quality rules today.</p>
    </section>
  )
}
