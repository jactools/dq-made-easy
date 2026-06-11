import React, { useEffect, useMemo, useRef, useState } from 'react'
import { AppButton, AppInput, AppModal, AppSelect, AppStack } from './app-primitives'
import { snakeToCamel } from '../utils/caseConverters'
import './OnboardingRuleReview.css'

export type OnboardingStatusFilter = 'all' | 'selected' | 'deselected' | 'already-covered'

export interface OnboardingReviewAttribute {
  attributeId: string
  name: string
  dataType: string
  alreadyCovered: boolean
}

export interface OnboardingReviewObjectGroup {
  dataObjectVersionId: string
  objectName: string
  datasetName: string
  count: number
  attributes: OnboardingReviewAttribute[]
}

export interface OnboardingReviewTemplateGroup {
  templateId: string
  templateName: string
  dimension: string
  checkType: string
  totalCount: number
  byDataset: Record<string, OnboardingReviewObjectGroup[]>
}

export interface OnboardingReviewResponse {
  scopeType: 'workspace' | 'product' | 'dataset' | 'object'
  scopeId: string
  totalAttributes: number
  totalProposals: number
  proposals: OnboardingReviewTemplateGroup[]
  generatedAt: string
}

export interface OnboardingReviewUiState {
  selectedProposalIds: string[]
  expandedTemplateIds: string[]
  expandedDatasetKeys: string[]
  expandedObjectKeys: string[]
  lazyLoadedObjectKeys: string[]
  dimensionFilter: string
  templateFilter: string
  datasetSearch: string
  dataTypeFilter: string
  statusFilter: OnboardingStatusFilter
}

interface OnboardingRuleReviewProps {
  isOpen: boolean
  response: OnboardingReviewResponse | Record<string, unknown> | null
  onClose: () => void
  onCreateDraftRules: (selectedProposalIds: string[]) => void
  onBackToScopeSelection?: () => void
  isCreatingDrafts?: boolean
  onRequestObjectAttributes?: (args: {
    templateId: string
    datasetId: string
    dataObjectVersionId: string
  }) => Promise<void>
  initialUiState?: OnboardingReviewUiState | null
  onUiStateChange?: (state: OnboardingReviewUiState) => void
}

const DATASET_FALLBACK = 'unassigned'
const OBJECT_LAZY_LOAD_THRESHOLD = 50

const toProposalId = (templateId: string, dataObjectVersionId: string, attributeId: string): string =>
  `${templateId}::${dataObjectVersionId}::${attributeId}`

const normalizeResponse = (
  response: OnboardingReviewResponse | Record<string, unknown> | null,
): OnboardingReviewResponse | null => {
  if (!response) {
    return null
  }

  const normalized = snakeToCamel<OnboardingReviewResponse>(response)
  return normalized
}

const getUniqueSorted = (values: string[]): string[] => Array.from(new Set(values)).sort((a, b) => a.localeCompare(b))

const flattenSelectableProposalIds = (groups: OnboardingReviewTemplateGroup[]): Set<string> => {
  const proposalIds = new Set<string>()

  groups.forEach((group) => {
    Object.values(group.byDataset || {}).forEach((objectGroups) => {
      objectGroups.forEach((objectGroup) => {
        objectGroup.attributes.forEach((attribute) => {
          if (attribute.alreadyCovered) {
            return
          }
          proposalIds.add(toProposalId(group.templateId, objectGroup.dataObjectVersionId, attribute.attributeId))
        })
      })
    })
  })

  return proposalIds
}

const collectProposalIdsForTemplate = (group: OnboardingReviewTemplateGroup): string[] => {
  const proposalIds: string[] = []

  Object.values(group.byDataset || {}).forEach((objectGroups) => {
    objectGroups.forEach((objectGroup) => {
      objectGroup.attributes.forEach((attribute) => {
        if (attribute.alreadyCovered) {
          return
        }
        proposalIds.push(toProposalId(group.templateId, objectGroup.dataObjectVersionId, attribute.attributeId))
      })
    })
  })

  return proposalIds
}

const collectProposalIdsForDataset = (templateGroup: OnboardingReviewTemplateGroup, datasetId: string): string[] => {
  const proposalIds: string[] = []

  ;(templateGroup.byDataset[datasetId] || []).forEach((objectGroup) => {
    objectGroup.attributes.forEach((attribute) => {
      if (attribute.alreadyCovered) {
        return
      }
      proposalIds.push(toProposalId(templateGroup.templateId, objectGroup.dataObjectVersionId, attribute.attributeId))
    })
  })

  return proposalIds
}

const collectProposalIdsForObject = (templateId: string, objectGroup: OnboardingReviewObjectGroup): string[] => {
  return objectGroup.attributes
    .filter((attribute) => !attribute.alreadyCovered)
    .map((attribute) => toProposalId(templateId, objectGroup.dataObjectVersionId, attribute.attributeId))
}

export const OnboardingRuleReview: React.FC<OnboardingRuleReviewProps> = ({
  isOpen,
  response,
  onClose,
  onCreateDraftRules,
  onBackToScopeSelection,
  isCreatingDrafts = false,
  onRequestObjectAttributes,
  initialUiState,
  onUiStateChange,
}) => {
  const normalizedResponse = useMemo(() => normalizeResponse(response), [response])
  const proposals = normalizedResponse?.proposals || []

  const [expandedTemplateIds, setExpandedTemplateIds] = useState<Set<string>>(new Set())
  const [expandedDatasetKeys, setExpandedDatasetKeys] = useState<Set<string>>(new Set())
  const [expandedObjectKeys, setExpandedObjectKeys] = useState<Set<string>>(new Set())
  const [lazyLoadedObjectKeys, setLazyLoadedObjectKeys] = useState<Set<string>>(new Set())

  const [dimensionFilter, setDimensionFilter] = useState('all')
  const [templateFilter, setTemplateFilter] = useState('all')
  const [datasetSearch, setDatasetSearch] = useState('')
  const [dataTypeFilter, setDataTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState<OnboardingStatusFilter>('all')
  const wasOpenRef = useRef(false)

  const selectableProposalIds = useMemo(() => flattenSelectableProposalIds(proposals), [proposals])

  const [selectedProposalIds, setSelectedProposalIds] = useState<Set<string>>(() => {
    const defaults = new Set<string>()
    selectableProposalIds.forEach((proposalId) => defaults.add(proposalId))
    return defaults
  })

  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      if (initialUiState) {
        setSelectedProposalIds(new Set(initialUiState.selectedProposalIds || []))
        setExpandedTemplateIds(new Set(initialUiState.expandedTemplateIds || []))
        setExpandedDatasetKeys(new Set(initialUiState.expandedDatasetKeys || []))
        setExpandedObjectKeys(new Set(initialUiState.expandedObjectKeys || []))
        setLazyLoadedObjectKeys(new Set(initialUiState.lazyLoadedObjectKeys || []))
        setDimensionFilter(initialUiState.dimensionFilter || 'all')
        setTemplateFilter(initialUiState.templateFilter || 'all')
        setDatasetSearch(initialUiState.datasetSearch || '')
        setDataTypeFilter(initialUiState.dataTypeFilter || 'all')
        setStatusFilter(initialUiState.statusFilter || 'all')
      } else {
        setExpandedTemplateIds(new Set())
        setExpandedDatasetKeys(new Set())
        setExpandedObjectKeys(new Set())
        setLazyLoadedObjectKeys(new Set())
        setDimensionFilter('all')
        setTemplateFilter('all')
        setDatasetSearch('')
        setDataTypeFilter('all')
        setStatusFilter('all')
        setSelectedProposalIds(new Set(selectableProposalIds))
      }
    }

    wasOpenRef.current = isOpen
  }, [initialUiState, isOpen, selectableProposalIds])

  useEffect(() => {
    setSelectedProposalIds((current) => {
      const next = new Set(Array.from(current).filter((proposalId) => selectableProposalIds.has(proposalId)))
      if (next.size === current.size) {
        return current
      }
      return next
    })
  }, [selectableProposalIds])

  useEffect(() => {
    if (!isOpen || !onUiStateChange) {
      return
    }

    onUiStateChange({
      selectedProposalIds: Array.from(selectedProposalIds),
      expandedTemplateIds: Array.from(expandedTemplateIds),
      expandedDatasetKeys: Array.from(expandedDatasetKeys),
      expandedObjectKeys: Array.from(expandedObjectKeys),
      lazyLoadedObjectKeys: Array.from(lazyLoadedObjectKeys),
      dimensionFilter,
      templateFilter,
      datasetSearch,
      dataTypeFilter,
      statusFilter,
    })
  }, [
    dataTypeFilter,
    datasetSearch,
    dimensionFilter,
    expandedDatasetKeys,
    expandedObjectKeys,
    expandedTemplateIds,
    isOpen,
    lazyLoadedObjectKeys,
    onUiStateChange,
    selectedProposalIds,
    statusFilter,
    templateFilter,
  ])

  const counts = useMemo(() => {
    const totalAttributes = proposals.reduce((acc, group) => {
      const byDataset = group.byDataset || {}
      return (
        acc +
        Object.values(byDataset).reduce((datasetAcc, objectGroups) => {
          return datasetAcc + objectGroups.reduce((objectAcc, objectGroup) => objectAcc + objectGroup.attributes.length, 0)
        }, 0)
      )
    }, 0)

    const alreadyCovered = proposals.reduce((acc, group) => {
      const byDataset = group.byDataset || {}
      return (
        acc +
        Object.values(byDataset).reduce((datasetAcc, objectGroups) => {
          return (
            datasetAcc +
            objectGroups.reduce(
              (objectAcc, objectGroup) =>
                objectAcc + objectGroup.attributes.filter((attribute) => attribute.alreadyCovered).length,
              0,
            )
          )
        }, 0)
      )
    }, 0)

    return {
      totalAttributes,
      alreadyCovered,
      selected: selectedProposalIds.size,
      selectable: selectableProposalIds.size,
    }
  }, [proposals, selectableProposalIds, selectedProposalIds])

  const allDimensions = useMemo(() => getUniqueSorted(proposals.map((group) => group.dimension)), [proposals])
  const allTemplates = useMemo(() => getUniqueSorted(proposals.map((group) => group.templateName)), [proposals])

  const allDataTypes = useMemo(() => {
    const types: string[] = []
    proposals.forEach((group) => {
      Object.values(group.byDataset || {}).forEach((objectGroups) => {
        objectGroups.forEach((objectGroup) => {
          objectGroup.attributes.forEach((attribute) => {
            types.push(attribute.dataType)
          })
        })
      })
    })
    return getUniqueSorted(types)
  }, [proposals])

  const filteredProposals = useMemo(() => {
    const lowerSearch = datasetSearch.trim().toLowerCase()

    return proposals
      .filter((group) => (dimensionFilter === 'all' ? true : group.dimension === dimensionFilter))
      .filter((group) => (templateFilter === 'all' ? true : group.templateName === templateFilter))
      .map((group) => {
        const filteredByDataset: Record<string, OnboardingReviewObjectGroup[]> = {}

        Object.entries(group.byDataset || {}).forEach(([datasetId, objectGroups]) => {
          const matchingObjectGroups = objectGroups
            .map((objectGroup) => {
              const matchingAttributes = objectGroup.attributes.filter((attribute) => {
                if (dataTypeFilter !== 'all' && attribute.dataType !== dataTypeFilter) {
                  return false
                }

                const proposalId = toProposalId(group.templateId, objectGroup.dataObjectVersionId, attribute.attributeId)
                const isSelected = selectedProposalIds.has(proposalId)

                if (statusFilter === 'selected' && !isSelected) {
                  return false
                }

                if (statusFilter === 'deselected' && (isSelected || attribute.alreadyCovered)) {
                  return false
                }

                if (statusFilter === 'already-covered' && !attribute.alreadyCovered) {
                  return false
                }

                if (statusFilter === 'all') {
                  return true
                }

                return true
              })

              return {
                ...objectGroup,
                attributes: matchingAttributes,
              }
            })
            .filter((objectGroup) => objectGroup.attributes.length > 0)

          if (matchingObjectGroups.length === 0) {
            return
          }

          const datasetName = matchingObjectGroups[0].datasetName || datasetId || DATASET_FALLBACK
          if (lowerSearch && !datasetName.toLowerCase().includes(lowerSearch)) {
            return
          }

          filteredByDataset[datasetId] = matchingObjectGroups
        })

        return {
          ...group,
          byDataset: filteredByDataset,
        }
      })
      .filter((group) => Object.keys(group.byDataset).length > 0)
  }, [proposals, dimensionFilter, templateFilter, datasetSearch, dataTypeFilter, statusFilter, selectedProposalIds])

  const toggleSelection = (proposalIds: string[], shouldSelect: boolean) => {
    setSelectedProposalIds((current) => {
      const next = new Set(current)
      proposalIds.forEach((proposalId) => {
        if (!selectableProposalIds.has(proposalId)) {
          return
        }

        if (shouldSelect) {
          next.add(proposalId)
          return
        }

        next.delete(proposalId)
      })
      return next
    })
  }

  const isGroupFullySelected = (proposalIds: string[]): boolean => {
    if (proposalIds.length === 0) {
      return false
    }
    return proposalIds.every((proposalId) => selectedProposalIds.has(proposalId))
  }

  const handleToggleTemplate = (templateId: string) => {
    setExpandedTemplateIds((current) => {
      const next = new Set(current)
      if (next.has(templateId)) {
        next.delete(templateId)
      } else {
        next.add(templateId)
      }
      return next
    })
  }

  const handleToggleDataset = (templateId: string, datasetId: string) => {
    const key = `${templateId}::${datasetId}`
    setExpandedDatasetKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  const handleToggleObject = async (
    templateId: string,
    datasetId: string,
    objectGroup: OnboardingReviewObjectGroup,
  ): Promise<void> => {
    const key = `${templateId}::${datasetId}::${objectGroup.dataObjectVersionId}`

    setExpandedObjectKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })

    if (objectGroup.count >= OBJECT_LAZY_LOAD_THRESHOLD && !lazyLoadedObjectKeys.has(key) && onRequestObjectAttributes) {
      await onRequestObjectAttributes({
        templateId,
        datasetId,
        dataObjectVersionId: objectGroup.dataObjectVersionId,
      })
      setLazyLoadedObjectKeys((current) => {
        const next = new Set(current)
        next.add(key)
        return next
      })
    }
  }

  const footer = (
    <div className="onboarding-review__footer-actions">
      {onBackToScopeSelection ? (
        <AppButton variant="secondary" onClick={onBackToScopeSelection} disabled={isCreatingDrafts}>
          Back to Scope Selection
        </AppButton>
      ) : null}
      <AppButton variant="secondary" onClick={onClose} disabled={isCreatingDrafts}>
        Cancel
      </AppButton>
      <AppButton
        variant="primary"
        onClick={() => onCreateDraftRules(Array.from(selectedProposalIds))}
        disabled={selectedProposalIds.size === 0 || isCreatingDrafts}
      >
        {isCreatingDrafts ? 'Creating Draft Rules...' : `Create ${selectedProposalIds.size} Draft Rules`}
      </AppButton>
    </div>
  )

  return (
    <AppModal isOpen={isOpen} onClose={onClose} title="Review Suggested Rules" size="xl" footer={footer}>
      <AppStack gap="md">
        <div className="onboarding-review__filters" data-testid="onboarding-review-filters">
          <AppSelect
            id="dimension-filter"
            label="Dimension"
            value={dimensionFilter}
            onChange={setDimensionFilter}
            options={[
              { value: 'all', label: 'All dimensions' },
              ...allDimensions.map((value) => ({ value, label: value })),
            ]}
          />
          <AppSelect
            id="template-filter"
            label="Template"
            value={templateFilter}
            onChange={setTemplateFilter}
            options={[
              { value: 'all', label: 'All templates' },
              ...allTemplates.map((value) => ({ value, label: value })),
            ]}
          />
          <AppInput
            id="dataset-filter"
            label="Dataset Search"
            value={datasetSearch}
            onChange={(event) => setDatasetSearch(event.target.value)}
            placeholder="Search dataset"
          />
          <AppSelect
            id="datatype-filter"
            label="Data Type"
            value={dataTypeFilter}
            onChange={setDataTypeFilter}
            options={[
              { value: 'all', label: 'All data types' },
              ...allDataTypes.map((value) => ({ value, label: value })),
            ]}
          />
          <AppSelect
            id="status-filter"
            label="Status"
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as OnboardingStatusFilter)}
            options={[
              { value: 'all', label: 'All' },
              { value: 'selected', label: 'Selected' },
              { value: 'deselected', label: 'De-selected' },
              { value: 'already-covered', label: 'Already covered' },
            ]}
          />
        </div>

        <div className="onboarding-review__tree" data-testid="onboarding-review-tree">
          {filteredProposals.length === 0 ? (
            <div className="onboarding-review__empty">No proposals match the current filters.</div>
          ) : (
            filteredProposals.map((templateGroup) => {
              const templateExpanded = expandedTemplateIds.has(templateGroup.templateId)
              const templateProposalIds = collectProposalIdsForTemplate(templateGroup)
              const templateSelected = isGroupFullySelected(templateProposalIds)

              return (
                <div className="onboarding-review__template" key={templateGroup.templateId}>
                  <div className="onboarding-review__row onboarding-review__row--template">
                    <button
                      type="button"
                      className="onboarding-review__toggle"
                      onClick={() => handleToggleTemplate(templateGroup.templateId)}
                      aria-label={templateExpanded ? 'Collapse template group' : 'Expand template group'}
                    >
                      {templateExpanded ? '▾' : '▸'}
                    </button>
                    <input
                      type="checkbox"
                      checked={templateSelected}
                      onChange={(event) => toggleSelection(templateProposalIds, event.target.checked)}
                      aria-label={`Select template ${templateGroup.templateName}`}
                    />
                    <div className="onboarding-review__row-label">
                      <strong>{templateGroup.templateName}</strong>
                      <span className="onboarding-review__meta">{templateGroup.dimension} · {templateGroup.totalCount}</span>
                    </div>
                  </div>

                  {templateExpanded
                    ? Object.entries(templateGroup.byDataset).map(([datasetId, objectGroups]) => {
                        const datasetName = objectGroups[0]?.datasetName || datasetId || DATASET_FALLBACK
                        const datasetKey = `${templateGroup.templateId}::${datasetId}`
                        const datasetExpanded = expandedDatasetKeys.has(datasetKey)
                        const datasetProposalIds = collectProposalIdsForDataset(templateGroup, datasetId)
                        const datasetSelected = isGroupFullySelected(datasetProposalIds)

                        return (
                          <div className="onboarding-review__dataset" key={datasetKey}>
                            <div className="onboarding-review__row onboarding-review__row--dataset">
                              <button
                                type="button"
                                className="onboarding-review__toggle"
                                onClick={() => handleToggleDataset(templateGroup.templateId, datasetId)}
                                aria-label={datasetExpanded ? 'Collapse dataset group' : 'Expand dataset group'}
                              >
                                {datasetExpanded ? '▾' : '▸'}
                              </button>
                              <input
                                type="checkbox"
                                checked={datasetSelected}
                                onChange={(event) => toggleSelection(datasetProposalIds, event.target.checked)}
                                aria-label={`Select dataset ${datasetName}`}
                              />
                              <div className="onboarding-review__row-label">
                                <span>{datasetName}</span>
                                <span className="onboarding-review__meta">{datasetProposalIds.length} selectable</span>
                              </div>
                            </div>

                            {datasetExpanded
                              ? objectGroups.map((objectGroup) => {
                                  const objectKey = `${datasetKey}::${objectGroup.dataObjectVersionId}`
                                  const objectExpanded = expandedObjectKeys.has(objectKey)
                                  const objectProposalIds = collectProposalIdsForObject(templateGroup.templateId, objectGroup)
                                  const objectSelected = isGroupFullySelected(objectProposalIds)

                                  return (
                                    <div className="onboarding-review__object" key={objectKey}>
                                      <div className="onboarding-review__row onboarding-review__row--object">
                                        <button
                                          type="button"
                                          className="onboarding-review__toggle"
                                          onClick={() => {
                                            void handleToggleObject(templateGroup.templateId, datasetId, objectGroup)
                                          }}
                                          aria-label={objectExpanded ? 'Collapse object group' : 'Expand object group'}
                                        >
                                          {objectExpanded ? '▾' : '▸'}
                                        </button>
                                        <input
                                          type="checkbox"
                                          checked={objectSelected}
                                          onChange={(event) => toggleSelection(objectProposalIds, event.target.checked)}
                                          aria-label={`Select object ${objectGroup.objectName}`}
                                        />
                                        <div className="onboarding-review__row-label">
                                          <span>{objectGroup.objectName}</span>
                                          <span className="onboarding-review__meta">{objectGroup.count} attributes</span>
                                        </div>
                                      </div>

                                      {objectExpanded ? (
                                        <div className="onboarding-review__attributes">
                                          {objectGroup.attributes.map((attribute) => {
                                            const proposalId = toProposalId(
                                              templateGroup.templateId,
                                              objectGroup.dataObjectVersionId,
                                              attribute.attributeId,
                                            )
                                            const isSelected = selectedProposalIds.has(proposalId)

                                            return (
                                              <label
                                                key={proposalId}
                                                className={[
                                                  'onboarding-review__attribute',
                                                  attribute.alreadyCovered ? 'onboarding-review__attribute--covered' : '',
                                                ]
                                                  .filter(Boolean)
                                                  .join(' ')}
                                              >
                                                <input
                                                  type="checkbox"
                                                  checked={isSelected}
                                                  disabled={attribute.alreadyCovered}
                                                  onChange={(event) => toggleSelection([proposalId], event.target.checked)}
                                                  aria-label={`Select attribute ${attribute.name}`}
                                                />
                                                <span>{attribute.name}</span>
                                                <span className="onboarding-review__attribute-type">{attribute.dataType}</span>
                                                {attribute.alreadyCovered ? (
                                                  <span className="onboarding-review__covered-badge">already covered</span>
                                                ) : null}
                                              </label>
                                            )
                                          })}
                                        </div>
                                      ) : null}
                                    </div>
                                  )
                                })
                              : null}
                          </div>
                        )
                      })
                    : null}
                </div>
              )
            })
          )}
        </div>

        <div className="onboarding-review__summary" data-testid="onboarding-review-summary">
          <span>{counts.selected} rules selected</span>
          <span>{counts.alreadyCovered} already covered</span>
          <span>{counts.totalAttributes} total</span>
          <AppButton
            variant="primary"
            onClick={() => onCreateDraftRules(Array.from(selectedProposalIds))}
            disabled={counts.selected === 0 || isCreatingDrafts}
          >
            {isCreatingDrafts ? 'Creating...' : `Create ${counts.selected} draft rules`}
          </AppButton>
        </div>
      </AppStack>
    </AppModal>
  )
}
