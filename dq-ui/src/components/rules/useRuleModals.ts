import { useCallback, useState } from 'react'

type ModalType =
  | 'submit'
  | 'deactivate'
  | 'approve'
  | 'activate'
  | 'template'
  | 'assign'
  | 'join'
  | 'test'
  | 'adhoc-run'
  | 'filter'
  | 'reusable-join'
  | 'edit'

interface ValidationDiagnosticsModalState {
  result: any
  ruleName: string
}

export const useRuleModals = () => {
  const [activeModalRule, setActiveModalRule] = useState<string | null>(null)
  const [activeModalType, setActiveModalType] = useState<ModalType | null>(null)
  const [activeModalReadOnly, setActiveModalReadOnly] = useState<boolean>(false)
  const [testDetailsRuleId, setTestDetailsRuleId] = useState<string | null>(null)
  const [validationDiagnosticsModal, setValidationDiagnosticsModal] = useState<ValidationDiagnosticsModalState | null>(null)

  const closeActiveModal = useCallback(() => {
    setActiveModalType(null)
    setActiveModalRule(null)
    setActiveModalReadOnly(false)
  }, [])

  const openActionModal = useCallback((ruleId: string, type: ModalType, readOnly = false) => {
    setActiveModalRule(ruleId)
    setActiveModalType(type)
    setActiveModalReadOnly(readOnly)
  }, [])

  const openTestDetails = useCallback((ruleId: string) => {
    setTestDetailsRuleId(ruleId)
  }, [])

  const closeTestDetails = useCallback(() => {
    setTestDetailsRuleId(null)
  }, [])

  const closeValidationDiagnostics = useCallback(() => {
    setValidationDiagnosticsModal(null)
  }, [])

  return {
    activeModalRule,
    activeModalType,
    activeModalReadOnly,
    setActiveModalRule,
    setActiveModalType,
    setActiveModalReadOnly,
    closeActiveModal,
    openActionModal,
    testDetailsRuleId,
    openTestDetails,
    closeTestDetails,
    validationDiagnosticsModal,
    setValidationDiagnosticsModal,
    closeValidationDiagnostics,
  }
}
