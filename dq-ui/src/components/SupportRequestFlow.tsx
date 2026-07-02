import React, { useCallback, useState } from 'react'

import { TertiaryButton } from './Button'
import { StatusBanner } from './StatusBanner'
import { SupportRequestSubmitButton, type SupportRequestResponse } from './SupportRequestSubmitButton'

type SupportRequestPayload = Record<string, unknown>

type SupportRequestFlowProps = {
  apiBaseUrl: string
  buttonLabel: string
  createRequestBody: () => SupportRequestPayload
  onSuccess?: (response: SupportRequestResponse) => void
  onError: (message: string) => void
  onDismiss?: () => void
  className?: string
  disabled?: boolean
}

type SupportRequestSuccessState = {
  message: string
  referenceId: string
  ticketUrl: string | null
}

export const SupportRequestFlow: React.FC<SupportRequestFlowProps> = ({
  apiBaseUrl,
  buttonLabel,
  createRequestBody,
  onSuccess,
  onError,
  onDismiss,
  className,
  disabled = false,
}) => {
  const [supportRequestSuccess, setSupportRequestSuccess] = useState<SupportRequestSuccessState | null>(null)

  const handleSuccess = useCallback((response: SupportRequestResponse) => {
    setSupportRequestSuccess({
      message: response.message,
      referenceId: response.referenceId,
      ticketUrl: response.ticketUrl || null,
    })

    if (response.mailtoUrl) {
      window.open(response.mailtoUrl, '_blank', 'noopener,noreferrer')
    }

    onSuccess?.(response)
  }, [onSuccess])

  const clearSuccess = useCallback(() => {
    setSupportRequestSuccess(null)
    onDismiss?.()
  }, [onDismiss])

  const openSupportTicket = useCallback((ticketUrl: string) => {
    window.open(ticketUrl, '_blank', 'noopener,noreferrer')
  }, [])

  return (
    <div className={className}>
      <SupportRequestSubmitButton
        apiBaseUrl={apiBaseUrl}
        buttonLabel={buttonLabel}
        createRequestBody={createRequestBody}
        onSuccess={handleSuccess}
        onError={onError}
        disabled={disabled}
      />

      {supportRequestSuccess && (
        <div style={{ marginTop: 16 }}>
          <StatusBanner
            variant="success"
            message={supportRequestSuccess.message}
            onDismiss={clearSuccess}
            referenceId={supportRequestSuccess.referenceId}
            secondaryAction={supportRequestSuccess.ticketUrl ? (
              <TertiaryButton onClick={() => openSupportTicket(supportRequestSuccess.ticketUrl || '')}>
                Open ticket
              </TertiaryButton>
            ) : undefined}
          />
        </div>
      )}
    </div>
  )
}