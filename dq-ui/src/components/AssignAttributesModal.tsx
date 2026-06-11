import React, { useState, useEffect, useMemo } from 'react'
import { PrimaryButton, SecondaryButton } from './Button'
import { AppSelect } from './app-primitives'
import { AppIcon, AppInput } from './app-primitives'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { useUnsavedChangesConfirmation } from '../hooks/useUnsavedChangesConfirmation'
import { useEnrichedValidation } from '../hooks/useEnrichedValidation'
import { AliasDiagnosticsDisplay } from './AliasDiagnosticsDisplay'
import { useAuth, useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { AttributeCard } from './rules/AttributeCard'
import { WorkspaceScopeSegmentedControl, type WorkspaceScope } from './WorkspaceScopeSegmentedControl'
import { DEFAULT_SEARCH_MINIMUM_LENGTH, matchesTokenizedSearch } from '../utils/listFilterState'
import './AssignAttributesModal.css'

const unwrapPage = (responseBody: any): any[] =>
  Array.isArray(responseBody?.data) ? responseBody.data : (Array.isArray(responseBody) ? responseBody : [])

interface Attribute {
  id: string
  name: string
  type: string
  description?: string
  table?: string
  dataObjectName?: string
  datasetName?: string
  dataProductName?: string
  dataObjectOwner?: string
  datasetOwner?: string
  dataProductOwner?: string
  workspaceId?: string
}

interface AssignAttributesModalProps {
  isOpen: boolean
  onClose: () => void
  ruleId?: string
  ruleVersionId?: string
  ruleName: string
  ruleExpression?: string
  currentAttributeIds: string[]
  currentAliasMappings?: Record<string, { attributeId: string; expectedDataType?: string; actualDataType?: string; compatible?: boolean }>
  /** When the rule uses the THRESHOLD check type, pass it here to show override inputs. */
  checkType?: string
  /** The rule-level default threshold (from checkTypeParams.threshold). */
  defaultThreshold?: number
  /** Existing per-attribute threshold overrides to seed the form with. */
  currentThresholdOverrides?: Record<string, number | undefined>
  onSave: (
    attributeIds: string[],
    aliasMappings?: Record<string, { attributeId: string; expectedDataType?: string; actualDataType?: string; compatible?: boolean }>,
    thresholdOverrides?: Record<string, number | undefined>
  ) => Promise<void>
}

type LogicalType = 'number' | 'string' | 'boolean' | 'date' | 'unknown'

const normalizeDataType = (rawType: string): LogicalType => {
  const value = String(rawType || '').toLowerCase()
  if (!value) return 'unknown'
  if (/int|decimal|numeric|number|double|float|real|money/.test(value)) return 'number'
  if (/bool/.test(value)) return 'boolean'
  if (/date|time|timestamp/.test(value)) return 'date'
  if (/char|text|string|uuid|json|xml/.test(value)) return 'string'
  return 'unknown'
}

const areTypesCompatible = (expected: LogicalType, actual: LogicalType): boolean => {
  if (expected === 'unknown' || actual === 'unknown') return true
  return expected === actual
}

const inferAliasExpectations = (expression: string): Array<{ alias: string; expected: LogicalType }> => {
  const source = String(expression || '')
  if (!source.trim()) return []
  const sourceWithoutLiterals = source
    .replace(/'(?:''|[^'])*'/g, ' ')
    .replace(/"(?:\\"|[^"])*"/g, ' ')
    .replace(/\[(?:\\.|[^\]])*\]/g, ' ')
    .replace(/\/(?:\\.|[^\/\n])+\/[gimsuy]*/g, ' ')

  const expectations = new Map<string, LogicalType>()
  const reserved = new Set([
    'and', 'or', 'not', 'is', 'null', 'in', 'like', 'rlike', 'between', 'true', 'false',
    'select', 'from', 'where', 'case', 'when', 'then', 'else', 'end', 'now', 'curdate',
    'count', 'sum', 'avg', 'min', 'max', 'length', 'trim', 'regexp_replace', 'interval', 'day',
  ])

  const pushExpectation = (aliasRaw: string, expected: LogicalType) => {
    const alias = String(aliasRaw || '').trim()
    if (!alias || reserved.has(alias.toLowerCase())) return
    if (/^\d/.test(alias)) return
    if (expectations.has(alias) && expectations.get(alias) !== expected) {
      expectations.set(alias, 'unknown')
      return
    }
    expectations.set(alias, expected)
  }

  const comparisonRegex = /\b([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|=|!=|>|<|like|rlike|~|!~)\s*(-?\d+(?:\.\d+)?|true|false|'(?:''|[^'])*'|"(?:\\"|[^"])*")/gi
  let match: RegExpExecArray | null
  while ((match = comparisonRegex.exec(source)) !== null) {
    const [, alias, , literal] = match
    const lit = String(literal || '').trim()
    if (/^-?\d+(?:\.\d+)?$/.test(lit)) {
      pushExpectation(alias, 'number')
    } else if (/^(true|false)$/i.test(lit)) {
      pushExpectation(alias, 'boolean')
    } else if (/^['"]/.test(lit)) {
      pushExpectation(alias, 'string')
    }
  }

  const tokenRegex = /\b([A-Za-z_][A-Za-z0-9_]*)\b/g
  while ((match = tokenRegex.exec(sourceWithoutLiterals)) !== null) {
    const token = match[1]
    if (reserved.has(token.toLowerCase())) continue
    if (!expectations.has(token)) {
      expectations.set(token, 'unknown')
    }
  }

  return Array.from(expectations.entries()).map(([alias, expected]) => ({ alias, expected }))
}

export const AssignAttributesModal: React.FC<AssignAttributesModalProps> = ({
  isOpen,
  onClose,
  ruleId,
  ruleVersionId,
  ruleName,
  ruleExpression,
  currentAttributeIds,
  currentAliasMappings,
  checkType,
  defaultThreshold,
  currentThresholdOverrides,
  onSave
}) => {
  const settings = useSettings()
  const auth = useAuth()
  const apiBaseUrl = toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl)
  const { enrichValidation } = useEnrichedValidation()
  
  const [attributes, setAttributes] = useState<Attribute[]>([])
  const [selectedAttributeIds, setSelectedAttributeIds] = useState<Set<string>>(new Set(currentAttributeIds))
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedScope, setSelectedScope] = useState<WorkspaceScope>('my')
  const [selectedTable, setSelectedTable] = useState<string>('all')
  const [selectedType, setSelectedType] = useState<string>('all')
  const [aliasMappings, setAliasMappings] = useState<Record<string, string>>({})
  const [thresholdOverrides, setThresholdOverrides] = useState<Record<string, number | undefined>>({})
  const [error, setError] = useState<string | null>(null)
  const [enrichedResult, setEnrichedResult] = useState<any>(null)
  const [enrichmentLoading, setEnrichmentLoading] = useState(false)
  
  const currentWorkspaceId = auth.currentWorkspaceId || auth.user?.workspaceRoles?.[0]?.workspaceId || null

  const userTokens = useMemo(
    () => new Set(
      [
        auth.user?.id,
        auth.user?.email,
        auth.user?.name,
        (auth.user as any)?.username,
        (auth.user as any)?.preferred_username,
        (auth.user as any)?.upn,
        (auth.user as any)?.sub,
      ]
        .map((value) => String(value || '').trim().toLowerCase())
        .filter(Boolean),
    ),
    [auth.user],
  )

  // Track if form has been modified
  const hasModifications = useMemo(() => {
    const initialIds = new Set(currentAttributeIds)
    const currentlySelected = selectedAttributeIds
    
    if (initialIds.size !== currentlySelected.size) return true
    for (const id of initialIds) {
      if (!currentlySelected.has(id)) return true
    }

    const initialMappings = Object.entries(currentAliasMappings || {}).reduce<Record<string, string>>((acc, [alias, mapping]) => {
      const attributeId = String((mapping as any)?.attributeId || '').trim()
      if (attributeId) acc[alias] = attributeId
      return acc
    }, {})

    if (JSON.stringify(initialMappings) !== JSON.stringify(aliasMappings)) return true

    // Detect threshold override changes
    if (JSON.stringify(thresholdOverrides) !== JSON.stringify(currentThresholdOverrides || {})) return true

    return false
  }, [selectedAttributeIds, currentAttributeIds, aliasMappings, currentAliasMappings, thresholdOverrides, currentThresholdOverrides])

  // Use reusable unsaved changes confirmation hook
  const {
    showConfirmation,
    handleCloseWithConfirmation,
    handleConfirmClose,
    handleCancelConfirmation,
  } = useUnsavedChangesConfirmation({
    isOpen,
    hasChanges: hasModifications,
    onClose,
  })

  useEffect(() => {
    if (isOpen) {
      loadAttributes()
      setSelectedAttributeIds(new Set(currentAttributeIds))
      const seedMappings = Object.entries(currentAliasMappings || {}).reduce<Record<string, string>>((acc, [alias, mapping]) => {
        const attributeId = String((mapping as any)?.attributeId || '').trim()
        if (attributeId) acc[alias] = attributeId
        return acc
      }, {})
      setAliasMappings(seedMappings)
      setSearchQuery('')
      setSelectedScope('my')
      setSelectedTable('all')
      setSelectedType('all')
    }
    setThresholdOverrides(currentThresholdOverrides ? { ...currentThresholdOverrides } : {})
  }, [isOpen, currentAttributeIds, currentAliasMappings])

  // Handle table/data object filter changes
  const handleTableFilterChange = (e: any) => {
    const value = typeof e === 'string' ? e : (e?.target?.value || e?.detail?.value)
    if (value !== undefined) {
      setSelectedTable(value)
    }
  }

  // Handle type filter changes
  const handleTypeFilterChange = (e: any) => {
    const value = typeof e === 'string' ? e : (e?.target?.value || e?.detail?.value)
    if (value !== undefined) {
      setSelectedType(value)
    }
  }

  const handleScopeChange = (scope: WorkspaceScope) => {
    setSelectedScope(scope)
    setSelectedTable('all')
    setSelectedType('all')
  }

  const loadAttributes = async () => {
    const token = getAuthToken()
    if (!token) {
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      const authHeaders = { Authorization: `Bearer ${token}` }

      const fetchAllPages = async (endpoint: string): Promise<any[]> => {
        const limit = 100
        let page = 1
        let rows: any[] = []

        while (true) {
          const separator = endpoint.includes('?') ? '&' : '?'
          const response = await fetch(`${apiBaseUrl}/${endpoint}${separator}page=${page}&limit=${limit}`, {
            headers: authHeaders,
          })

          if (!response.ok) {
            throw new Error(`Failed to load ${endpoint}`)
          }

          const body = await response.json()
          const chunk = unwrapPage(body)
          const total = Number(body?.total ?? rows.length + chunk.length)
          rows = rows.concat(chunk)

          if (chunk.length === 0 || rows.length >= total || chunk.length < limit) {
            break
          }

          page += 1
        }

        return rows
      }

      const [attributeData, dataObjectData, dataSetData, dataProductData] = await Promise.all([
        fetchAllPages('attributes-catalog'),
        fetchAllPages('data-objects-catalog'),
        fetchAllPages('data-sets'),
        fetchAllPages('data-products'),
      ])

      const dataObjectsById = dataObjectData.reduce<Record<string, any>>((acc, dataObject) => {
        acc[dataObject.id] = dataObject
        return acc
      }, {})

      const dataSetsById = dataSetData.reduce<Record<string, any>>((acc, dataSet) => {
        acc[dataSet.id] = dataSet
        return acc
      }, {})

      const dataProductsById = dataProductData.reduce<Record<string, any>>((acc, dataProduct) => {
        acc[dataProduct.id] = dataProduct
        return acc
      }, {})

      const latestAttributes = attributeData
        .filter(attribute => {
          const dataObject = dataObjectsById[attribute.data_object_id]
          const latestVersionId = dataObject?.latest_version_id ?? dataObject?.latestVersionId
          return dataObject && (!latestVersionId || latestVersionId === attribute.version_id)
        })
        .map(attribute => {
          const dataObject = dataObjectsById[attribute.data_object_id]
          const dataSet = dataObject ? dataSetsById[dataObject.dataset_id] : undefined
          const dataProduct = dataSet?.product_id ? dataProductsById[dataSet.product_id] : undefined
          const owner = dataSet?.owner || dataProduct?.owner || undefined
          const workspaceId = dataSet?.workspace_id || dataProduct?.workspace_id || undefined

          return {
            id: attribute.id,
            name: attribute.name,
            type: attribute.type,
            description: attribute.description || undefined,
            table: dataObject?.name,
            dataObjectName: dataObject?.name,
            datasetName: dataSet?.name,
            dataProductName: dataProduct?.name,
            dataObjectOwner: owner,
            datasetOwner: dataSet?.owner || undefined,
            dataProductOwner: dataProduct?.owner || undefined,
            workspaceId,
          } as Attribute
        })

      setAttributes(latestAttributes)
    } catch (err: any) {
      setError(err.message || 'Failed to load attributes')
      console.error('Error loading attributes:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const scopedAttributes = useMemo(() => {
    return attributes.filter((attribute) => {
      if (selectedScope === 'global') {
        return true
      }

      const attributeWorkspaceId = String(attribute.workspaceId || '').trim()
      const currentWorkspace = String(currentWorkspaceId || '').trim()
      if (!attributeWorkspaceId || !currentWorkspace || attributeWorkspaceId !== currentWorkspace) {
        return false
      }

      if (selectedScope === 'all') {
        return true
      }

      const ownerToken = String(attribute.dataObjectOwner || attribute.datasetOwner || attribute.dataProductOwner || '').trim().toLowerCase()
      if (!ownerToken) {
        return false
      }

      if (selectedScope === 'team') {
        return !userTokens.has(ownerToken)
      }

      return userTokens.has(ownerToken)
    })
  }, [attributes, currentWorkspaceId, selectedScope, userTokens])

  const uniqueTables = useMemo(() => {
    const tables = new Set(scopedAttributes.map(a => a.table).filter(Boolean))
    return Array.from(tables).sort()
  }, [scopedAttributes])

  const uniqueTypes = useMemo(() => {
    const types = new Set(scopedAttributes.map(a => a.type).filter(Boolean))
    return Array.from(types).sort()
  }, [scopedAttributes])

  const filteredAttributes = useMemo(() => {
    let filtered = scopedAttributes

    if (selectedTable !== 'all') {
      filtered = filtered.filter(attr => attr.table === selectedTable)
    }

    if (selectedType !== 'all') {
      filtered = filtered.filter(attr => attr.type === selectedType)
    }

    if (searchQuery.trim()) {
      filtered = filtered.filter(attr =>
        matchesTokenizedSearch([
          attr.name,
          attr.id,
          attr.description,
          attr.table,
          attr.datasetName,
          attr.dataProductName,
        ], searchQuery)
      )
    }

    return filtered
  }, [scopedAttributes, searchQuery, selectedTable, selectedType])

  const aliasExpectations = useMemo(() => {
    const inferred = inferAliasExpectations(ruleExpression || '')
    const knownAttributeTokens = new Set(
      attributes.flatMap(attr => [String(attr.id || '').toLowerCase(), String(attr.name || '').toLowerCase()]).filter(Boolean)
    )

    return inferred.filter(item => !knownAttributeTokens.has(item.alias.toLowerCase()))
  }, [ruleExpression, attributes])

  const selectedAttributes = useMemo(() => {
    return attributes.filter(attr => selectedAttributeIds.has(attr.id))
  }, [attributes, selectedAttributeIds])

  const unavailableSelectedCount = useMemo(() => {
    const availableIds = new Set(scopedAttributes.map(attr => attr.id))
    let missing = 0
    selectedAttributeIds.forEach(id => {
      if (!availableIds.has(id)) missing += 1
    })
    return missing
  }, [scopedAttributes, selectedAttributeIds])

  useEffect(() => {
    if (attributes.length === 0) return
    const availableIds = new Set(attributes.map(attr => attr.id))
    setSelectedAttributeIds(prev => {
      const pruned = new Set(Array.from(prev).filter(id => availableIds.has(id)))
      return pruned.size === prev.size ? prev : pruned
    })
  }, [attributes])

  const singleAliasMode = aliasExpectations.length === 1

  const aliasValidation = useMemo(() => {
    const issues: string[] = []

    // If there is a single business alias in the expression (e.g. "balance"),
    // validate selected attributes directly against its expected type.
    if (singleAliasMode) {
      const alias = aliasExpectations[0]
      const nextDetails = selectedAttributes.map(attr => {
        const actualType = normalizeDataType(attr.type || '')
        const compatible = areTypesCompatible(alias.expected, actualType)
        if (!compatible) {
          issues.push(
            `Business term "${alias.alias}" expects ${alias.expected}, but selected technical attribute "${attr.name}" is ${actualType}`,
          )
        }
        return {
          alias: alias.alias,
          expected: alias.expected,
          attributeId: attr.id,
          actualType,
          compatible,
        }
      })

      return { details: nextDetails, issues }
    }

    const nextDetails = aliasExpectations.map((item) => {
      const mappedAttributeId = aliasMappings[item.alias] || ''
      const selectedAttribute = selectedAttributes.find(attr => attr.id === mappedAttributeId)
      const actualType = selectedAttribute ? normalizeDataType(selectedAttribute.type || '') : 'unknown'
      const compatible = selectedAttribute ? areTypesCompatible(item.expected, actualType) : false

      if (!mappedAttributeId) {
        issues.push(`Business term "${item.alias}" is not mapped to a technical attribute`)
      } else if (!selectedAttribute) {
        issues.push(`Business term "${item.alias}" must map to a selected technical attribute`)
      } else if (!compatible) {
        issues.push(
          `Business term "${item.alias}" expects ${item.expected} but technical attribute "${selectedAttribute.name}" is ${actualType}`,
        )
      }

      return {
        alias: item.alias,
        expected: item.expected,
        attributeId: mappedAttributeId,
        actualType,
        compatible,
      }
    })

    return { details: nextDetails, issues }
  }, [aliasExpectations, aliasMappings, selectedAttributes, singleAliasMode])

  const normalizedRuleId = String(ruleId || '').trim()
  const normalizedRuleVersionId = String(ruleVersionId || '').trim()

  // Fetch enriched validation when aliases or mappings change
  useEffect(() => {
    if (!isOpen) return
    if (aliasExpectations.length === 0 || !ruleExpression) {
      setEnrichedResult(null)
      return
    }
    if (!normalizedRuleId || !normalizedRuleVersionId) {
      setEnrichedResult(null)
      return
    }
    
    const fetchEnrichment = async () => {
      setEnrichmentLoading(true)
      try {
        const unresolvedList = aliasExpectations
          .filter(a => !aliasMappings[a.alias])
          .map(a => a.alias)

        const result = await enrichValidation({
          ruleId: normalizedRuleId,
          ruleVersionId: normalizedRuleVersionId,
          expression: ruleExpression,
          detectedAliases: aliasExpectations.map(a => a.alias),
          unresolvedAliases: unresolvedList,
          issues: aliasValidation.issues,
          manualAliasMappings: aliasMappings,
        })
        
        // Map resolved term names to available attributes
        const enrichedWithAttributeIds = { ...result }
        if (enrichedWithAttributeIds.diagnostics) {
          Object.entries(enrichedWithAttributeIds.diagnostics).forEach(([alias, diagnostic]) => {
            const resolvedTermName = (diagnostic as any).resolvedTermName
            if (resolvedTermName && attributes.length > 0) {
              // Match by name (case-insensitive prefix match)
              const matchingAttr = attributes.find(attr => 
                attr.name.toLowerCase().includes(resolvedTermName.toLowerCase()) ||
                resolvedTermName.toLowerCase().includes(attr.name.toLowerCase())
              )
              if (matchingAttr) {
                (diagnostic as any).resolvedAttributeId = matchingAttr.id
              }
            }
          })
        }
        
        setEnrichedResult(enrichedWithAttributeIds)
      } catch (err) {
        console.error('Failed to fetch enriched validation:', err)
        setEnrichedResult(null)
      } finally {
        setEnrichmentLoading(false)
      }
    }

    fetchEnrichment()
  }, [
    isOpen,
    aliasExpectations,
    aliasMappings,
    aliasValidation.issues,
    enrichValidation,
    ruleExpression,
    attributes,
    normalizedRuleId,
    normalizedRuleVersionId,
  ])

  const toggleAttribute = (attrId: string) => {
    setSelectedAttributeIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(attrId)) {
        newSet.delete(attrId)
      } else {
        newSet.add(attrId)
      }
      return newSet
    })
  }

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)
    try {
      if (aliasValidation.issues.length > 0) {
        throw new Error(aliasValidation.issues[0])
      }

      const normalizedAliasMappings = aliasValidation.details.reduce<Record<string, { attributeId: string; expectedDataType?: string; actualDataType?: string; compatible?: boolean }>>((acc, item) => {
        if (!item.attributeId) return acc
        // In single-alias mode we keep one representative mapping for backend storage.
        if (singleAliasMode && acc[item.alias]) return acc
        acc[item.alias] = {
          attributeId: item.attributeId,
          expectedDataType: item.expected,
          actualDataType: item.actualType,
          compatible: item.compatible,
        }
        return acc
      }, {})

      // Only pass overrides when the rule uses THRESHOLD check type
      const overridesToSave = checkType === 'THRESHOLD' && Object.keys(thresholdOverrides).length > 0
        ? thresholdOverrides
        : undefined
      await onSave(selectedAttributes.map(attr => attr.id), normalizedAliasMappings, overridesToSave)
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to save technical attribute assignments')
      console.error('Error saving:', err)
    } finally {
      setIsSaving(false)
    }
  }

  const handleSelectAll = () => {
    setSelectedAttributeIds(new Set(filteredAttributes.map(a => a.id)))
  }

  const handleClearAll = () => {
    setSelectedAttributeIds(new Set())
  }

  if (!isOpen) return null

  return (
    <>
      <div className="assign-modal-overlay" onClick={handleCloseWithConfirmation}>
        <div className="assign-modal-content assign-attributes-modal" onClick={e => e.stopPropagation()}>
          <div className="assign-modal-header">
            <h2>Map Business Terms to Technical Attributes</h2>
            <button className="assign-modal-close" onClick={handleCloseWithConfirmation} aria-label="Close">
              <AppIcon name="times" />
            </button>
          </div>

        <div className="assign-modal-body">
          <div className="rule-info">
            <strong>Rule:</strong> {ruleName}
          </div>

          {error && (
            <div className="error-message">
              <AppIcon name="exclamation-circle" />
              {error}
            </div>
          )}

          <div className="filters-section">
            <div className="filter-row">
              <div className="filter-group scope-filter-group">
                <WorkspaceScopeSegmentedControl
                  value={selectedScope}
                  onChange={handleScopeChange}
                  ariaLabel="Technical attribute catalog scope"
                  label="Scope:"
                  className="scope-filter-buttons"
                  controlClassName="scope-filter-control"
                  labelClassName="filter-label"
                />
              </div>
            </div>

            <div className="filter-row">
              <AppInput
                label="Search technical attributes"
                type="text"
                placeholder="Search technical attributes..."
                value={searchQuery}
                onChange={(e: any) => {
                  const value = e?.target?.value ?? e?.detail?.value ?? ''
                  setSearchQuery(String(value || ''))
                }}
                onInput={(e: any) => {
                  const value = e?.target?.value ?? e?.detail?.value ?? ''
                  setSearchQuery(String(value || ''))
                }}
                className="search-input"
              />
              <div className="attribute-search-threshold">Search applies at {DEFAULT_SEARCH_MINIMUM_LENGTH}+ characters.</div>
            </div>
            
            <div className="filter-row">
              <div className="filter-group">
                <AppSelect
                  label="Data Object"
                  labelClassName="filter-label"
                  value={selectedTable}
                  onChange={handleTableFilterChange}
                  options={[
                    { value: 'all', label: `All (${attributes.length})` },
                    ...uniqueTables.map(table => {
                      const count = attributes.filter(a => a.table === table).length
                      return { value: table, label: `${table} (${count})` }
                    }),
                  ]}
                />
              </div>

              <div className="filter-group">
                <AppSelect
                  label="Type"
                  labelClassName="filter-label"
                  value={selectedType}
                  onChange={handleTypeFilterChange}
                  options={[
                    { value: 'all', label: 'All Types' },
                    ...uniqueTypes.map(type => {
                      const count = attributes.filter(a => a.type === type).length
                      return { value: type, label: `${type} (${count})` }
                    }),
                  ]}
                />
              </div>
            </div>

            <div className="filter-row bulk-actions-row">
              <div className="filter-results">
                Showing {filteredAttributes.length} of {scopedAttributes.length} technical attributes
              </div>
              <div className="bulk-actions">
                <button className="link-button" onClick={handleSelectAll}>
                  Select All ({filteredAttributes.length})
                </button>
                <button className="link-button" onClick={handleClearAll}>
                  Clear All
                </button>
              </div>
            </div>
          </div>

          <div className="selection-summary">
            {selectedAttributes.length} technical attribute{selectedAttributes.length !== 1 ? 's' : ''} selected
            {unavailableSelectedCount > 0 && (
              <span> ({unavailableSelectedCount} unavailable from current catalog)</span>
            )}
          </div>

          {aliasExpectations.length > 0 && (
            <div className="alias-mapping-section">
              <div className="alias-mapping-header">
                <strong>Business Terms</strong>
                <span>
                  {singleAliasMode
                    ? `Business term "${aliasExpectations[0].alias}" is validated against all selected technical attributes`
                    : 'Map business terms used in the rule expression to selected technical attributes'}
                </span>
              </div>

              {enrichedResult && !enrichmentLoading && (
                <div className="enriched-diagnostics-section">
                  <AliasDiagnosticsDisplay
                    diagnostics={enrichedResult.diagnostics || {}}
                    catalogAvailable={enrichedResult.catalogAvailable !== false}
                    lastSync={enrichedResult.lastSync}
                  />
                </div>
              )}

              {enrichmentLoading && (
                <div className="enrichment-loading">
                  <AppIcon name="arrow-circle-repeat" style={{ animation: 'spin 1s linear infinite' }} />
                  Checking catalog for business term suggestions...
                </div>
              )}

              <div className="alias-mapping-list">
                {singleAliasMode ? (
                  selectedAttributes.map((attr) => {
                    const alias = aliasExpectations[0]
                    const actualType = normalizeDataType(attr.type || '')
                    const compatible = areTypesCompatible(alias.expected, actualType)
                    return (
                      <div key={`${alias.alias}-${attr.id}`} className="alias-mapping-row">
                        <div className="alias-meta">
                          <div className="alias-name">{alias.alias}</div>
                          <div className="alias-type">Expected technical type: {alias.expected}</div>
                        </div>
                        <div className="alias-select-wrapper">
                          <div className="attribute-name">{attr.name} ({attr.type || 'unknown'})</div>
                        </div>
                        <div className={`alias-compat ${compatible ? 'ok' : 'error'}`}>
                          {compatible ? `Compatible (${actualType})` : `Incompatible (${actualType})`}
                        </div>
                      </div>
                    )
                  })
                ) : (
                aliasValidation.details.map((item) => {
                  const diagnostic = enrichedResult?.diagnostics?.[item.alias]
                  const suggestionAttributeId = diagnostic?.resolvedAttributeId
                  const suggestionSource = diagnostic?.source
                  const suggestionConfidence = diagnostic?.confidence
                  
                  return (
                    <div key={item.alias} className="alias-mapping-row">
                      <div className="alias-meta">
                        <div className="alias-name">{item.alias}</div>
                        <div className="alias-type">Expected technical type: {item.expected}</div>
                      </div>
                      <div className="alias-select-wrapper">
                        <AppSelect
                          label={`Technical attribute for ${item.alias}`}
                          value={item.attributeId || ''}
                          onChange={(value: string) => {
                            setAliasMappings(prev => ({ ...prev, [item.alias]: String(value || '') }))
                          }}
                          placeholderLabel="Select technical attribute"
                          options={filteredAttributes.map(attr => ({
                            value: attr.id,
                            label: `${attr.name} (${attr.type || 'unknown'})`,
                          }))}
                        />
                        
                        {/* Show suggestion badge if available and not yet selected */}
                        {suggestionSource && !item.attributeId && (
                          <div className="suggestion-badge">
                            <span className={`source-badge ${suggestionSource.toLowerCase()}`}>
                              {suggestionSource === 'catalog' && '📚 Catalog'}
                              {suggestionSource === 'manual' && '✏️ Manual'}
                              {suggestionSource === 'unresolved' && '⚠️ Unresolved'}
                            </span>
                            {suggestionConfidence && suggestionConfidence < 1.0 && (
                              <span className="confidence">{Math.round(suggestionConfidence * 100)}%</span>
                            )}
                            <button 
                              className="apply-suggestion-btn"
                              onClick={() => {
                                if (suggestionAttributeId) {
                                  setAliasMappings(prev => ({ ...prev, [item.alias]: suggestionAttributeId }))
                                }
                              }}
                              title="Apply this suggestion"
                            >
                              Apply
                            </button>
                          </div>
                        )}
                      </div>
                      <div className={`alias-compat ${item.compatible ? 'ok' : 'error'}`}>
                        {item.attributeId
                          ? item.compatible
                            ? `Compatible (${item.actualType})`
                            : `Incompatible (${item.actualType})`
                          : 'Not mapped'}
                      </div>
                    </div>
                  )
                }))}
              </div>
            </div>
          )}

          {isLoading ? (
            <div className="loading-state">
              <AppIcon name="arrow-circle-repeat" style={{ animation: 'spin 1s linear infinite' }} />
              Loading technical attributes...
            </div>
          ) : (
            <div className="attributes-list">
              {filteredAttributes.length === 0 ? (
                <div className="empty-state">
                  {searchQuery || selectedTable !== 'all' || selectedType !== 'all' || selectedScope !== 'all'
                    ? 'No technical attributes match the current scope or filters'
                    : 'No technical attributes available'}
                </div>
              ) : (
                filteredAttributes.map(attr => (
                  <label key={attr.id} className="attribute-item">
                    <input
                      type="checkbox"
                      checked={selectedAttributeIds.has(attr.id)}
                      onChange={() => toggleAttribute(attr.id)}
                    />
                    <AttributeCard
                      attribute={attr}
                      badge={
                        (attr.type || attr.description)
                          ? (
                            <span className="rule-attribute-source">
                              {[attr.type, attr.description].filter(Boolean).join(' · ')}
                            </span>
                          )
                          : undefined
                      }
                    />
                    {checkType === 'THRESHOLD' && selectedAttributeIds.has(attr.id) && (
                      <div className="attribute-threshold-override" onClick={e => e.preventDefault()}>
                        <label
                          className="attribute-threshold-label"
                          htmlFor={`threshold-override-${attr.id}`}
                        >
                          Threshold&nbsp;%
                        </label>
                        <input
                          id={`threshold-override-${attr.id}`}
                          type="number"
                          min={0}
                          max={100}
                          step={0.1}
                          className="attribute-threshold-input"
                          placeholder={defaultThreshold != null ? String(defaultThreshold) : 'rule default'}
                          value={thresholdOverrides[attr.id] ?? ''}
                          onChange={e => {
                            const raw = e.target.value
                            setThresholdOverrides(prev => ({
                              ...prev,
                              [attr.id]: raw === '' ? undefined : parseFloat(raw),
                            }))
                          }}
                        />
                        {thresholdOverrides[attr.id] != null && (
                          <button
                            type="button"
                            className="attribute-threshold-reset"
                            title="Reset to rule default"
                            onClick={e => {
                              e.preventDefault()
                              setThresholdOverrides(prev => ({ ...prev, [attr.id]: undefined }))
                            }}
                          >
                            ×
                          </button>
                        )}
                      </div>
                    )}
                  </label>
                ))
              )}
            </div>
          )}
        </div>

        <div className="assign-modal-footer">
          <SecondaryButton onClick={handleCloseWithConfirmation} disabled={isSaving}>
            Cancel
          </SecondaryButton>
          <PrimaryButton
            onClick={handleSave}
            disabled={isSaving || isLoading || aliasValidation.issues.length > 0}
          >
            {isSaving ? 'Saving...' : `Save (${selectedAttributes.length})`}
          </PrimaryButton>
        </div>
      </div>
    </div>

    <UnsavedChangesDialog
      isOpen={showConfirmation}
      onConfirm={handleConfirmClose}
      onCancel={handleCancelConfirmation}
    />
    </>
  )
}
