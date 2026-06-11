import React from 'react'
import { ModalShell } from '../ModalShell'

export type AppModalProps = React.ComponentProps<typeof ModalShell>

export const AppModal: React.FC<AppModalProps> = (props) => {
  return <ModalShell {...props} />
}