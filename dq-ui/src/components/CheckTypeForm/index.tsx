import React from 'react'
import { RuleCheckType, RuleCheckTypeParams } from '../../types/rules'
import { ThresholdForm } from './ThresholdForm'
import { RowCountForm } from './RowCountForm'
import { RegexForm } from './RegexForm'
import { RangeForm } from './RangeForm'
import { AllowlistForm } from './AllowlistForm'
import { CorrectForm } from './CorrectForm'
import { UniquenessForm } from './UniquenessForm'
import { PlausibleForm } from './PlausibleForm'
import { PresentForm } from './PresentForm'
import { ReferentialIntegrityForm } from './ReferentialIntegrityForm'
import { ReconcileForm } from './ReconcileForm'
import { TimelinessForm } from './TimelinessForm'
import { TransferMatchForm } from './TransferMatchForm'
import { JoinConsistencyForm } from './JoinConsistencyForm'
import { ActualityDateConfig } from './ActualityDateConfig'
import { JoinConsistencyFieldErrors } from './joinConsistencyValidation'
import { CheckTypeFieldErrors } from './checkTypeValidation'
import './CheckTypeForm.css'
import './ActualityDateConfig.css'

export { ActualityDateConfig } from './ActualityDateConfig'
export type { ActualityDateFieldErrors } from './ActualityDateConfig'

interface CheckTypeFormProps {
  checkType: RuleCheckType
  params: Partial<RuleCheckTypeParams>
  onChange: (params: RuleCheckTypeParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

export const CheckTypeForm: React.FC<CheckTypeFormProps> = ({
  checkType,
  params,
  onChange,
  fieldErrors,
  catalogAttributeName,
}) => {
  switch (checkType) {
    case 'THRESHOLD':
      return <ThresholdForm params={params as any} onChange={onChange} fieldErrors={fieldErrors} catalogAttributeName={catalogAttributeName} />
    case 'ROW_COUNT':
      return <RowCountForm params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} />
    case 'REGEX':
      return <RegexForm params={params as any} onChange={onChange} fieldErrors={fieldErrors} catalogAttributeName={catalogAttributeName} />
    case 'RANGE':
      return <RangeForm params={params as any} onChange={onChange} fieldErrors={fieldErrors} catalogAttributeName={catalogAttributeName} />
    case 'ALLOWLIST':
    case 'BLOCKLIST':
      return <AllowlistForm checkType={checkType} params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} catalogAttributeName={catalogAttributeName} />
    case 'UNIQUENESS':
      return <UniquenessForm params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} />
    case 'REFERENTIAL_INTEGRITY':
      return <ReferentialIntegrityForm params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} catalogAttributeName={catalogAttributeName} />
    case 'FRESHNESS':
    case 'LAG':
    case 'FUTURE_DATE':
      return <TimelinessForm checkType={checkType} params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} catalogAttributeName={catalogAttributeName} />
    case 'PRESENT':
      return <PresentForm params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} catalogAttributeName={catalogAttributeName} />
    case 'CORRECT':
      return <CorrectForm params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} />
    case 'RECONCILE':
      return <ReconcileForm params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} />
    case 'PLAUSIBLE':
      return <PlausibleForm params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} catalogAttributeName={catalogAttributeName} />
    case 'TRANSFER_MATCH':
      return <TransferMatchForm params={params as any} onChange={onChange as any} fieldErrors={fieldErrors} />
    case 'JOIN_CONSISTENCY':
      return (
        <JoinConsistencyForm
          params={params as any}
          onChange={onChange as any}
          fieldErrors={fieldErrors as JoinConsistencyFieldErrors}
        />
      )
    default:
      return (
        <p className="check-type-form-unsupported">
          Parameter form for <strong>{checkType}</strong> is not yet available.
          Use the expression field below to define the check manually.
        </p>
      )
  }
}
