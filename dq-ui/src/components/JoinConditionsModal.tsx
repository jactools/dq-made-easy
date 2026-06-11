import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PrimaryButton, SecondaryButton } from './Button'
import { AppSelect } from './app-primitives'
import { AppBanner, AppIcon, AppModal, AppPanel, AppStack } from './app-primitives'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { useUnsavedChangesConfirmation } from '../hooks/useUnsavedChangesConfirmation'
import { useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { RuleJoinCondition, RuleJoinDefinition } from '../types/rules'
import { createSupportReferenceId, formatSupportReferenceId } from '../utils/supportReference'
import './JoinConditionsModal.css'

interface DataObject {
  id: string
  name: string
  latestVersionId?: string
}

interface Attribute {
  id: string
  name: string
  dataObjectId?: string
}

interface JoinConditionsModalProps {
  isOpen: boolean
  onClose: () => void
  onOpenDataAssets: () => void
  ruleName: string
  workspaceId?: string
  currentJoinConditions?: RuleJoinDefinition[]
  onSave: (joinConditions: RuleJoinDefinition[]) => Promise<void>
}

const emptyCondition = (): RuleJoinCondition => ({
  leftDataObjectId: '',
  leftAttributeId: '',
  rightDataObjectId: '',
  rightAttributeId: '',
  operator: '=',
})

const emptyJoinDefinition = (): RuleJoinDefinition => ({
  joinType: 'inner',
  conditions: [emptyCondition()],
})

const unwrapPage = (responseBody: any): any[] =>
  Array.isArray(responseBody?.data) ? responseBody.data : (Array.isArray(responseBody) ? responseBody : [])

export const JoinConditionsModal: React.FC<JoinConditionsModalProps> = ({
  isOpen,
  onClose,
  onOpenDataAssets,
  ruleName,
  workspaceId,
  currentJoinConditions,
  onSave,
}) => {
  const settings = useSettings()
  const dataCatalogApiBase = toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl)
  const rulebuilderApiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)

  const [dataObjects, setDataObjects] = useState<DataObject[]>([])
  const [attributes, setAttributes] = useState<Attribute[]>([])
  const [joinDefinitions, setJoinDefinitions] = useState<RuleJoinDefinition[]>([emptyJoinDefinition()])
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copyNotice, setCopyNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const errorReferenceId = useMemo(() => (error ? createSupportReferenceId() : null), [error])
  const copyNoticeReferenceId = useMemo(
    () => (copyNotice?.type === 'error' ? createSupportReferenceId() : null),
    [copyNotice]
  )
  const openDataAssetsAfterCloseRef = useRef(false)

  // Track if form has been modified
  const initialJoinDefinitions = useMemo(() => {
    const existingDefinitions = Array.isArray(currentJoinConditions)
      ? currentJoinConditions.filter(def => def && Array.isArray(def.conditions))
      : []
    return existingDefinitions.length > 0 ? existingDefinitions : [emptyJoinDefinition()]
  }, [currentJoinConditions])

  const hasChanges = useMemo(() => {
    // Check if join definitions have changed
    if (JSON.stringify(joinDefinitions) !== JSON.stringify(initialJoinDefinitions)) return true
    return false
  }, [joinDefinitions, initialJoinDefinitions])

  const handleModalClose = useCallback(() => {
    onClose()
    if (openDataAssetsAfterCloseRef.current) {
      openDataAssetsAfterCloseRef.current = false
      onOpenDataAssets()
    }
  }, [onClose, onOpenDataAssets])

  // Use reusable unsaved changes confirmation hook
  const {
    showConfirmation,
    handleCloseWithConfirmation,
    handleConfirmClose,
    handleCancelConfirmation,
  } = useUnsavedChangesConfirmation({
    isOpen,
    hasChanges,
    onClose: handleModalClose,
  })

  const handleCancelCloseConfirmation = useCallback(() => {
    openDataAssetsAfterCloseRef.current = false
    handleCancelConfirmation()
  }, [handleCancelConfirmation])

  useEffect(() => {
    if (!isOpen) return

    const existingDefinitions = Array.isArray(currentJoinConditions)
      ? currentJoinConditions.filter(def => def && Array.isArray(def.conditions))
      : []

    if (existingDefinitions.length > 0) {
      setJoinDefinitions(
        existingDefinitions.map(def => ({
          joinType: def.joinType || 'inner',
          conditions: def.conditions.length > 0 ? def.conditions : [emptyCondition()],
        }))
      )
    } else {
      setJoinDefinitions([emptyJoinDefinition()])
    }

    const loadCatalog = async () => {
      const token = getAuthToken()
      if (!token) {
        setIsLoading(false)
        return
      }
      setIsLoading(true)
      setError(null)
      try {
        const authHeaders = { Authorization: `Bearer ${token}` }
        const dataObjectsResponse = await fetch(`${dataCatalogApiBase}/data-objects-catalog?limit=100`, {
          headers: authHeaders,
        })

        if (!dataObjectsResponse.ok) {
          throw new Error('Failed to load data object metadata')
        }

        const loadedDataObjects = unwrapPage(await dataObjectsResponse.json())

        const nextDataObjects = loadedDataObjects.map(dataObject => ({
          id: dataObject.id,
          name: dataObject.name,
          latestVersionId: dataObject.latest_version_id,
        }))

        const versionToObjectId = nextDataObjects.reduce<Record<string, string>>((acc, item) => {
          if (item.latestVersionId) {
            acc[item.latestVersionId] = item.id
          }
          return acc
        }, {})

        const latestVersionIds = Object.keys(versionToObjectId)

        const attributesByVersion = await Promise.all(
          latestVersionIds.map(async versionId => {
            const response = await fetch(
              `${dataCatalogApiBase}/attributes-catalog?versionId=${encodeURIComponent(versionId)}&limit=100`,
              { headers: authHeaders }
            )

            if (!response.ok) {
              return [] as any[]
            }

            return unwrapPage(await response.json())
          })
        )

        const nextAttributes = attributesByVersion
          .flat()
          .map(attribute => ({
            id: attribute.id,
            name: attribute.name,
            dataObjectId: attribute.data_object_id || versionToObjectId[attribute.version_id],
          }))

        setDataObjects(nextDataObjects)
        setAttributes(nextAttributes)
      } catch (err: any) {
        setError(err?.message || 'Failed to load data object metadata')
      } finally {
        setIsLoading(false)
      }
    }

    loadCatalog()
  }, [isOpen, currentJoinConditions, dataCatalogApiBase])

  useEffect(() => {
    if (!copyNotice) return
    const timer = window.setTimeout(() => setCopyNotice(null), 2500)
    return () => window.clearTimeout(timer)
  }, [copyNotice])

  const attributesByObjectId = useMemo(() => {
    const byId: Record<string, Attribute[]> = {}

    dataObjects.forEach(obj => {
      byId[obj.id] = attributes.filter(attr => attr.dataObjectId === obj.id)
    })

    return byId
  }, [attributes, dataObjects])

  const dataObjectNameById = useMemo(() => {
    return dataObjects.reduce<Record<string, string>>((acc, dataObject) => {
      acc[dataObject.id] = dataObject.name
      return acc
    }, {})
  }, [dataObjects])

  const attributeNameById = useMemo(() => {
    return attributes.reduce<Record<string, string>>((acc, attribute) => {
      acc[attribute.id] = attribute.name
      return acc
    }, {})
  }, [attributes])

  const joinExpressionPreview = useMemo(() => {
    const clauses = joinDefinitions
      .map(joinDefinition => {
        const completeConditions = joinDefinition.conditions.filter(
          condition =>
            condition.leftDataObjectId &&
            condition.leftAttributeId &&
            condition.rightDataObjectId &&
            condition.rightAttributeId &&
            condition.operator
        )

        if (completeConditions.length === 0) {
          return ''
        }

        const conditionExpression = completeConditions
          .map(condition => {
            const leftObject = dataObjectNameById[condition.leftDataObjectId] || condition.leftDataObjectId
            const leftAttribute = attributeNameById[condition.leftAttributeId] || condition.leftAttributeId
            const rightObject = dataObjectNameById[condition.rightDataObjectId] || condition.rightDataObjectId
            const rightAttribute = attributeNameById[condition.rightAttributeId] || condition.rightAttributeId
            return `${leftObject}.${leftAttribute} ${condition.operator} ${rightObject}.${rightAttribute}`
          })
          .join(' AND ')

        return `${joinDefinition.joinType.toUpperCase()} JOIN ON ${conditionExpression}`
      })
      .filter(Boolean)

    return clauses.join('\n')
  }, [joinDefinitions, dataObjectNameById, attributeNameById])

  const updateJoinType = (joinIndex: number, value: RuleJoinDefinition['joinType']) => {
    setJoinDefinitions(prev =>
      prev.map((joinDef, i) => (i === joinIndex ? { ...joinDef, joinType: value } : joinDef))
    )
  }

  const updateCondition = (
    joinIndex: number,
    conditionIndex: number,
    field: keyof RuleJoinCondition,
    value: string
  ) => {
    setJoinDefinitions(prev =>
      prev.map((joinDef, i) => {
        if (i !== joinIndex) return joinDef

        const nextConditions = joinDef.conditions.map((condition, cIndex) => {
          if (cIndex !== conditionIndex) return condition

          const next = { ...condition, [field]: value }
          if (field === 'leftDataObjectId') {
            next.leftAttributeId = ''
          }
          if (field === 'rightDataObjectId') {
            next.rightAttributeId = ''
          }
          return next
        })

        return { ...joinDef, conditions: nextConditions }
      })
    )
  }

  const addCondition = (joinIndex: number) => {
    setJoinDefinitions(prev =>
      prev.map((joinDef, i) =>
        i === joinIndex ? { ...joinDef, conditions: [...joinDef.conditions, emptyCondition()] } : joinDef
      )
    )
  }

  const getSelectValue = (event: any): string => {
    if (typeof event === 'string') return event
    return event?.detail?.value ?? event?.target?.value ?? ''
  }

  const getFieldValue = (event: any): string => {
    return event?.detail?.value ?? event?.target?.value ?? event?.currentTarget?.value ?? ''
  }

  const removeCondition = (joinIndex: number, conditionIndex: number) => {
    setJoinDefinitions(prev =>
      prev.map((joinDef, i) => {
        if (i !== joinIndex) return joinDef

        const nextConditions = joinDef.conditions.filter((_, cIndex) => cIndex !== conditionIndex)
        return {
          ...joinDef,
          conditions: nextConditions.length > 0 ? nextConditions : [emptyCondition()],
        }
      })
    )
  }

  const addJoinDefinition = () => {
    setJoinDefinitions(prev => [...prev, emptyJoinDefinition()])
  }

  const removeJoinDefinition = (joinIndex: number) => {
    setJoinDefinitions(prev => {
      const next = prev.filter((_, index) => index !== joinIndex)
      return next.length > 0 ? next : [emptyJoinDefinition()]
    })
  }

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)

    const completeJoinDefinitions = joinDefinitions
      .map(joinDef => {
        const completeConditions = joinDef.conditions.filter(
          condition =>
            condition.leftDataObjectId &&
            condition.leftAttributeId &&
            condition.rightDataObjectId &&
            condition.rightAttributeId &&
            condition.operator
        )

        if (completeConditions.length === 0) {
          return null
        }

        return {
          joinType: joinDef.joinType,
          conditions: completeConditions,
        } as RuleJoinDefinition
      })
      .filter((joinDef): joinDef is RuleJoinDefinition => !!joinDef)

    try {
      if (completeJoinDefinitions.length === 0) {
        await onSave([])
      } else {
        await onSave(completeJoinDefinitions)
      }
      onClose()
    } catch (err: any) {
      setError(err?.message || 'Failed to save join conditions')
    } finally {
      setIsSaving(false)
    }
  }

  const copyToClipboard = async (value: string) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value)
      } else {
        const textArea = document.createElement('textarea')
        textArea.value = value
        textArea.setAttribute('readonly', '')
        textArea.style.position = 'fixed'
        textArea.style.opacity = '0'
        document.body.appendChild(textArea)
        textArea.select()
        document.execCommand('copy')
        document.body.removeChild(textArea)
      }

      setCopyNotice({ type: 'success', message: 'Join expression copied to clipboard.' })
    } catch {
      setCopyNotice({ type: 'error', message: 'Failed to copy join expression.' })
    }
  }

  const handleOpenDataAssets = useCallback(() => {
    openDataAssetsAfterCloseRef.current = true
    handleCloseWithConfirmation()
  }, [handleCloseWithConfirmation])

  return (
    <>
      <AppModal
        isOpen={isOpen}
        onClose={handleCloseWithConfirmation}
        title="Define Join Conditions"
        titleAs="h3"
        size="xl"
        dialogClassName="join-modal-content"
        bodyClassName="join-modal-body"
        footerClassName="join-modal-footer"
        footer={(
          <>
            <SecondaryButton onClick={handleCloseWithConfirmation} disabled={isSaving}>
              Cancel
            </SecondaryButton>
            <SecondaryButton
              onClick={handleOpenDataAssets}
              disabled={isLoading || isSaving}
            >
              Open Data Assets
            </SecondaryButton>
            <PrimaryButton onClick={handleSave} disabled={isLoading || isSaving}>
              {isSaving ? 'Saving...' : 'Save Join Conditions'}
            </PrimaryButton>
          </>
        )}
      >
        <AppStack gap="lg" className="join-modal-stack">
          <div className="join-rule-info">
            <strong>Rule:</strong> {ruleName}
          </div>

          {error && (
            <AppBanner variant="error">
              {error}
              {errorReferenceId && (
                <>
                  <br />
                  {formatSupportReferenceId(errorReferenceId)}
                </>
              )}
            </AppBanner>
          )}

        {isLoading ? (
          <div className="join-loading">Loading data object metadata...</div>
        ) : (
          <AppStack gap="lg" className="join-definitions-list">
            {joinDefinitions.map((joinDef, joinIndex) => (
              <AppPanel
                key={`join-definition-${joinIndex}`}
                className="join-definition-card"
                title={`Join ${joinIndex + 1}`}
                titleAs="h4"
                actions={(
                  <SecondaryButton
                    type="button"
                    className="join-definition-remove"
                    onClick={() => removeJoinDefinition(joinIndex)}
                    disabled={isSaving}
                  >
                    Remove Join
                  </SecondaryButton>
                )}
                bodyClassName="join-definition-card__body"
              >
                <div className="join-section">
                  <AppSelect
                    fieldClassName="join-select"
                    label={`Join ${joinIndex + 1} Type`}
                    labelClassName="join-label"
                    value={joinDef.joinType}
                    onChange={e => updateJoinType(joinIndex, getSelectValue(e) as RuleJoinDefinition['joinType'])}
                    disabled={isSaving}
                    options={[
                      { value: 'inner', label: 'INNER JOIN' },
                      { value: 'left', label: 'LEFT JOIN' },
                      { value: 'right', label: 'RIGHT JOIN' },
                      { value: 'full', label: 'FULL JOIN' },
                    ]}
                  />
                </div>

                <div className="join-conditions-list">
                  {joinDef.conditions.map((condition, conditionIndex) => {
                    const leftAttributes = attributesByObjectId[condition.leftDataObjectId] || []
                    const rightAttributes = attributesByObjectId[condition.rightDataObjectId] || []

                    return (
                      <div className="join-condition-row" key={`join-condition-${joinIndex}-${conditionIndex}`}>
                        <AppSelect
                          fieldClassName="join-select"
                          label="Left Data Object"
                          value={condition.leftDataObjectId}
                          onChange={e => updateCondition(joinIndex, conditionIndex, 'leftDataObjectId', getSelectValue(e))}
                          disabled={isSaving}
                          placeholderLabel="Left Data Object"
                          options={dataObjects.map(obj => ({ value: obj.id, label: obj.name }))}
                        />

                        <AppSelect
                          fieldClassName="join-select"
                          label="Left Attribute"
                          value={condition.leftAttributeId}
                          onChange={e => updateCondition(joinIndex, conditionIndex, 'leftAttributeId', getSelectValue(e))}
                          disabled={isSaving || !condition.leftDataObjectId}
                          placeholderLabel="Left Attribute"
                          options={leftAttributes.map(attr => ({ value: attr.id, label: attr.name }))}
                        />

                        <AppSelect
                          fieldClassName="join-select join-operator"
                          label="Operator"
                          value={condition.operator}
                          onChange={e => updateCondition(joinIndex, conditionIndex, 'operator', getSelectValue(e))}
                          disabled={isSaving}
                          options={[
                            { value: '=', label: '=' },
                            { value: '!=', label: '!=' },
                            { value: '>', label: '>' },
                            { value: '>=', label: '>=' },
                            { value: '<', label: '<' },
                            { value: '<=', label: '<=' },
                          ]}
                        />

                        <AppSelect
                          fieldClassName="join-select"
                          label="Right Data Object"
                          value={condition.rightDataObjectId}
                          onChange={e => updateCondition(joinIndex, conditionIndex, 'rightDataObjectId', getSelectValue(e))}
                          disabled={isSaving}
                          placeholderLabel="Right Data Object"
                          options={dataObjects.map(obj => ({ value: obj.id, label: obj.name }))}
                        />

                        <AppSelect
                          fieldClassName="join-select"
                          label="Right Attribute"
                          value={condition.rightAttributeId}
                          onChange={e => updateCondition(joinIndex, conditionIndex, 'rightAttributeId', getSelectValue(e))}
                          disabled={isSaving || !condition.rightDataObjectId}
                          placeholderLabel="Right Attribute"
                          options={rightAttributes.map(attr => ({ value: attr.id, label: attr.name }))}
                        />

                        <SecondaryButton
                          type="button"
                          className="join-remove"
                          onClick={() => removeCondition(joinIndex, conditionIndex)}
                          disabled={isSaving}
                        >
                          Remove
                        </SecondaryButton>
                      </div>
                    )
                  })}
                </div>

                <SecondaryButton
                  type="button"
                  className="join-add"
                  onClick={() => addCondition(joinIndex)}
                  disabled={isSaving}
                >
                  Add condition
                </SecondaryButton>
              </AppPanel>
            ))}

            <AppPanel
              className="join-expression-preview"
              title="Generated Join Expression (Preview)"
              titleAs="h4"
              bodyClassName="join-expression-preview__body"
            >
              {copyNotice && (
                <AppBanner variant={copyNotice.type}>
                  {copyNotice.message}
                  {copyNoticeReferenceId && (
                    <>
                      <br />
                      {formatSupportReferenceId(copyNoticeReferenceId)}
                    </>
                  )}
                </AppBanner>
              )}
              {joinExpressionPreview ? (
                <div className="join-expression-row">
                  <pre className="join-expression-code">{joinExpressionPreview}</pre>
                  <SecondaryButton
                    type="button"
                    className="join-expression-copy"
                    onClick={() => copyToClipboard(joinExpressionPreview)}
                    aria-label="Copy generated join expression"
                    title="Copy generated join expression"
                  >
                    <AppIcon name="copy" />
                  </SecondaryButton>
                </div>
              ) : (
                <p className="join-expression-empty">Complete join fields to preview the generated expression.</p>
              )}
            </AppPanel>
          </AppStack>
        )}

        <SecondaryButton
          type="button"
          className="join-add"
          onClick={addJoinDefinition}
          disabled={isLoading || isSaving}
        >
          Add join
        </SecondaryButton>

        <AppPanel
          tone="muted"
          className="join-save-as-reusable"
          title="Data Assets are the primary join authoring surface"
          titleAs="h4"
        >
          <p>Open Data Assets to create or evolve the join-backed business shape. Reusable joins remain available here for migration and assignment only.</p>
        </AppPanel>
      </AppStack>
    </AppModal>

      <UnsavedChangesDialog
        isOpen={showConfirmation}
        onConfirm={handleConfirmClose}
        onCancel={handleCancelCloseConfirmation}
      />
    </>
  )
}
