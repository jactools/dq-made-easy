import React, { useCallback, useState } from 'react'

import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { normalizeValidationUiText } from '../utils/validationTerminology'
import { SecondaryButton } from './Button'

type SupportRequestDeliveryMode = 'email' | 'itsm' | 'teams'

export type SupportRequestResponse = {
  referenceId: string
  deliveryModes: Array<SupportRequestDeliveryMode>
  message: string
  correlationId: string
  mailtoUrl?: string | null
  recipientEmail?: string | null
  ticketNumber?: string | null
  ticketSystem?: string | null
  ticketUrl?: string | null
}

type SupportRequestPayload = Record<string, unknown>

type SupportRequestSubmitButtonProps = {
  apiBaseUrl: string
  buttonLabel: string
  createRequestBody: () => SupportRequestPayload
  onSuccess: (response: SupportRequestResponse) => void
  onError: (message: string) => void
  className?: string
  disabled?: boolean
}

const formatReferenceId = (referenceId: string): string => {
  const normalized = String(referenceId || '').trim()
  return normalized ? `Reference ID: ${normalized}` : 'Reference ID: n/a'
}

const extractErrorMessage = (payload: unknown, fallback: string, status: number): string => {
  const detail = (payload as any)?.detail
  const referenceId = typeof detail?.reference_id === 'string'
    ? detail.reference_id
    : typeof (payload as any)?.reference_id === 'string'
      ? (payload as any).reference_id
      : null

  if (typeof detail === 'string') {
    const message = referenceId ? `${detail} (${formatReferenceId(referenceId)})` : detail
    return normalizeValidationUiText(message)
  }

  if (typeof detail?.message === 'string') {
    const message = referenceId ? `${detail.message} (${formatReferenceId(referenceId)})` : detail.message
    return normalizeValidationUiText(message)
  }

  if (typeof (payload as any)?.message === 'string') {
    const message = referenceId ? `${(payload as any).message} (${formatReferenceId(referenceId)})` : (payload as any).message
    return normalizeValidationUiText(message)
  }

  return normalizeValidationUiText(
    referenceId ? `${fallback} (${status}) - ${formatReferenceId(referenceId)}` : `${fallback} (${status})`
  )
}

export const SupportRequestSubmitButton: React.FC<SupportRequestSubmitButtonProps> = ({
  apiBaseUrl,
  buttonLabel,
  createRequestBody,
  onSuccess,
  onError,
  className,
  disabled = false,
}) => {
  const [pending, setPending] = useState(false)

  const handleClick = useCallback(async () => {
    if (disabled || pending) {
      return
    }

    setPending(true)

    try {
      const requestBody = camelToSnake(createRequestBody())
      const token = getAuthToken()
      const supportApiBase = toApiGroupV1Base('system', apiBaseUrl)
      const response = await fetch(`${supportApiBase}/support/requests`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(requestBody),
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        throw new Error(extractErrorMessage(payload, 'Failed to request assistance from operations', response.status))
      }

      const assistance = snakeToCamel<SupportRequestResponse>(payload)

      if (assistance.deliveryModes.includes('itsm') && !assistance.ticketNumber) {
        throw new Error('Backend returned an ITSM assistance response without a ticket number.')
      }

      onSuccess(assistance)
    } catch (exc) {
      onError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to request assistance from operations')
    } finally {
      setPending(false)
    }
  }, [apiBaseUrl, createRequestBody, disabled, onError, onSuccess, pending])

  return (
    <SecondaryButton onClick={() => void handleClick()} disabled={disabled || pending} className={className}>
      {pending ? 'Requesting…' : buttonLabel}
    </SecondaryButton>
  )
}