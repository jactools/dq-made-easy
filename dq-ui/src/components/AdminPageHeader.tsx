import React from 'react'
import { AppPageHeader } from './app-primitives'

type AdminPageHeaderProps = {
  title: React.ReactNode
  subtitle?: React.ReactNode
  actions?: React.ReactNode
  supplementary?: React.ReactNode
}

export const AdminPageHeader: React.FC<AdminPageHeaderProps> = ({ title, subtitle, actions, supplementary }) => {
  return (
    <AppPageHeader title={title} description={subtitle} actions={actions}>
      {supplementary}
    </AppPageHeader>
  )
}