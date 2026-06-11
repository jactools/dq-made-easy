import React, { useCallback, useEffect, useMemo, useState } from 'react'

import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { useDataProduct } from '../contexts/DataProductContext'
import { useSettings } from '../hooks/useContexts'
import { useAuth } from '../hooks/useKeycloak'
import type { DataAttribute, DataObject, DataObjectVersion, DataProduct, DataSet, DefinitionMappingTarget } from '../types/dataProducts'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { Button } from './Button'
import {
  AppBadge,
  AppEmptyState,
  AppPageHeader,
  AppPageShell,
  AppPanel,
  AppSelect,
  AppStack,
  AppToolbar,
} from './app-primitives'
import { StatusBanner } from './StatusBanner'
import { AppInput } from './app-primitives'
import './DefinitionMappingsPage.css'

const DEFINITION_MAPPING_TARGET_STORAGE_KEY = 'dq-definition-mapping-target'

type CatalogView = 'mappings' | 'reference-data'

type RegistryDefinitionValueDomain = {
  type?: string
  format?: string
  unit?: string
  allowedValues?: string[]
  constraints?: Record<string, unknown>
}

type RegistryDefinition = {
  definitionId: string
  definitionName: string
  definitionType?: string
  objectClass?: string
  property?: string
  businessDefinition?: string
  valueDomain?: RegistryDefinitionValueDomain
  glossaryId?: string
  glossaryName?: string
  owner?: string
  synonyms?: string[]
  parentDefinitionId?: string
  parentDefinitionName?: string
  childDefinitionIds?: string[]
  childDefinitionNames?: string[]
  childDefinitionCount?: number
  appliesTo?: string[]
}

type DataDefinitionTaskDefinition = {
  definitionId: string
  definitionName: string
  businessDefinition?: string
  examples?: string[]
  constraints?: string[]
  openQuestions?: string[]
  boardReviewStatus?: string
  status?: string
}

type DataDefinitionTaskResult = {
  reviewStatus?: string
  registryContract?: {
    glossary?: {
      name?: string
      displayName?: string
    }
    definitions?: DataDefinitionTaskDefinition[]
  }
  boardReviewPacket?: {
    boardName?: string
    reviewStatus?: string
    reviewSummary?: string
    approvalCriteria?: string[]
    openQuestions?: Array<{
      definitionId?: string
      questions?: string[]
    }>
    approval?: {
      status?: string
      approverName?: string
      approvalNotes?: string
      approvedAt?: string
    }
  }
  openmetadataImportResult?: {
    definitionCount?: number
    glossary?: {
      fullyQualifiedName?: string
    }
  }
  orchestrationTrace?: Array<{
    stepId?: string
    name?: string
    status?: string
    detail?: string
  }>
}

type DataDefinitionTaskStatus = {
  requestId: string
  currentWorkspaceId: string
  versionId?: string
  selectedAttributeIds: string[]
  prompt: string
  requestedByUserId?: string | null
  requestedByEmail?: string | null
  requestedAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
  status: 'pending' | 'started' | 'completed' | 'failed'
  errorMessage?: string | null
  analysisType: string
  analysisProvider: string
  autoImport: boolean
  taskPayload: Record<string, unknown>
  result?: DataDefinitionTaskResult | null
}

type DataDefinitionTaskStatusResponse = {
  success: boolean
  request: DataDefinitionTaskStatus
}

type DataDefinitionTaskHistoryResponse = {
  success: boolean
  requests: DataDefinitionTaskStatus[]
}

type DataDefinitionTaskCreateResponse = {
  success: boolean
  queued: boolean
  requestId: string
  eventsUrl: string
  message: string
}

type DataDefinitionTaskEvent = {
  requestId?: string
  status?: DataDefinitionTaskStatus['status']
  errorMessage?: string | null
  request?: DataDefinitionTaskStatus
}

type DataDefinitionTaskImportResponse = {
  success: boolean
  requestId: string
  message: string
}

const toStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item) => String(item || '').trim()).filter(Boolean)
}

const toValueDomain = (input: unknown): RegistryDefinitionValueDomain | undefined => {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    return undefined
  }

  const payload = input as Record<string, unknown>
  const valueDomain: RegistryDefinitionValueDomain = {
    type: String(payload.type || '').trim() || undefined,
    format: String(payload.format || '').trim() || undefined,
    unit: String(payload.unit || '').trim() || undefined,
    allowedValues: toStringArray(payload.allowedValues),
    constraints: payload.constraints && typeof payload.constraints === 'object' && !Array.isArray(payload.constraints)
      ? (payload.constraints as Record<string, unknown>)
      : {},
  }

  const allowedValues = valueDomain.allowedValues || []

  if (!valueDomain.type && !valueDomain.format && !valueDomain.unit && allowedValues.length === 0 && Object.keys(valueDomain.constraints || {}).length === 0) {
    return undefined
  }

  return valueDomain
}

const toTextLines = (value: string): string[] => value
  .split(/\n|,/)
  .map((item) => item.trim())
  .filter(Boolean)

const resolveTaskEventsUrl = (apiBase: string, eventsUrl: string): string => {
  const trimmed = eventsUrl.trim()
  if (!trimmed) {
    throw new Error('Data-definition task response did not include an event stream URL.')
  }
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed
  }
  if (trimmed.startsWith('/')) {
    const baseRoot = apiBase.replace(/\/data-catalog\/v1\/?$/i, '')
    return `${baseRoot}${trimmed}`
  }
  return `${apiBase.replace(/\/$/, '')}/${trimmed.replace(/^\/+/, '')}`
}

const parseDataDefinitionTaskEventFrame = (frame: string): DataDefinitionTaskEvent | null => {
  const dataLines: string[] = []
  frame.split(/\r?\n/).forEach((line) => {
    if (!line || line.startsWith(':')) {
      return
    }
    const separatorIndex = line.indexOf(':')
    const field = separatorIndex === -1 ? line : line.slice(0, separatorIndex)
    const value = separatorIndex === -1 ? '' : line.slice(separatorIndex + 1).replace(/^ /, '')
    if (field === 'data') {
      dataLines.push(value)
    }
  })
  if (dataLines.length === 0) {
    return null
  }
  return snakeToCamel<DataDefinitionTaskEvent>(JSON.parse(dataLines.join('\n')))
}

const buildDataDefinitionTaskEventsPath = (requestId: string): string => (
  `/data-catalog/v1/data-definition-tasks/requests/${encodeURIComponent(requestId)}/events`
)

const MAPPING_STATUS_LABELS: Record<string, string> = {
  explicit: 'Explicit mapping',
  inherited: 'Inherited from prior version',
  explicit_unmapped: 'Explicitly cleared on this version',
  inherited_unmapped: 'Inherited clear from prior version',
  unmapped: 'Not mapped',
}

const getMappingStatusTone = (status?: string): 'neutral' | 'info' | 'success' | 'warning' | 'error' => {
  switch (status) {
    case 'explicit':
      return 'info'
    case 'inherited':
      return 'success'
    case 'explicit_unmapped':
    case 'inherited_unmapped':
      return 'warning'
    case 'unmapped':
      return 'neutral'
    case 'completed':
      return 'success'
    case 'failed':
      return 'error'
    case 'started':
      return 'info'
    case 'pending':
      return 'neutral'
    default:
      return 'neutral'
  }
}

const toAttribute = (input: Record<string, unknown>): DataAttribute => ({
  id: String(input.id || ''),
  name: String(input.name || ''),
  type: String(input.type || 'string') as DataAttribute['type'],
  nullable: input.nullable !== false,
  description: String(input.description || '').trim() || undefined,
  format: String(input.format || '').trim() || undefined,
  isCde: Boolean(input.isCde),
  isPrimaryKey: Boolean(input.isPrimaryKey),
  ruleCount: Number(input.ruleCount || 0),
  definitionId: String(input.definitionId || '').trim() || undefined,
  definitionMappingStatus: (String(input.definitionMappingStatus || 'unmapped') as DataAttribute['definitionMappingStatus']) || 'unmapped',
  definitionMappingAttributeId: String(input.definitionMappingAttributeId || '').trim() || undefined,
  definitionMappingVersionId: String(input.definitionMappingVersionId || '').trim() || undefined,
  definitionMappingMappedBy: String(input.definitionMappingMappedBy || '').trim() || undefined,
  definitionMappingCreatedAt: String(input.definitionMappingCreatedAt || '').trim() || undefined,
  maskingMethod: String(input.maskingMethod || '').trim() || undefined,
  encryptionRequired: input.encryptionRequired === true,
  encryptionKeyId: String(input.encryptionKeyId || '').trim() || undefined,
  protectionConfiguredBy: String(input.protectionConfiguredBy || '').trim() || undefined,
  protectionUpdatedAt: String(input.protectionUpdatedAt || '').trim() || undefined,
})

const toDefinition = (input: Record<string, unknown>): RegistryDefinition => ({
  definitionId: String(input.definitionId || ''),
  definitionName: String(input.definitionName || ''),
  definitionType: String(input.definitionType || '').trim() || undefined,
  objectClass: String(input.objectClass || '').trim() || undefined,
  property: String(input.property || '').trim() || undefined,
  businessDefinition: String(input.businessDefinition || '').trim() || undefined,
  valueDomain: toValueDomain(input.valueDomain),
  glossaryId: String(input.glossaryId || '').trim() || undefined,
  glossaryName: String(input.glossaryName || '').trim() || undefined,
  owner: String(input.owner || '').trim() || undefined,
  synonyms: toStringArray(input.synonyms),
  parentDefinitionId: String(input.parentDefinitionId || '').trim() || undefined,
  parentDefinitionName: String(input.parentDefinitionName || '').trim() || undefined,
  childDefinitionIds: toStringArray(input.childDefinitionIds),
  childDefinitionNames: toStringArray(input.childDefinitionNames),
  childDefinitionCount: Number(input.childDefinitionCount || 0),
  appliesTo: toStringArray(input.appliesTo),
})

export const DefinitionMappingsPage: React.FC = () => {
  const getFieldValue = (event: any): string => {
    const detailValue = event?.detail?.value
    if (detailValue !== undefined && detailValue !== null) {
      return String(detailValue)
    }

    const targetValue = event?.target?.value
    if (targetValue !== undefined && targetValue !== null) {
      return String(targetValue)
    }

    return ''
  }

  const settings = useSettings()
  const auth = useAuth()
  const {
    state,
    filteredProducts,
    standaloneDatasets,
    loadDatasets,
    loadDataObjects,
    loadVersions,
    selectProduct,
    selectDataset,
    selectDataObject,
    selectVersion,
  } = useDataProduct()
  const apiBase = toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl)
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  const [selectedProductId, setSelectedProductId] = useState('')
  const [selectedDatasetId, setSelectedDatasetId] = useState('')
  const [selectedObjectId, setSelectedObjectId] = useState('')
  const [selectedVersionId, setSelectedVersionId] = useState('')
  const [activeCatalogView, setActiveCatalogView] = useState<CatalogView>('mappings')
  const [attributes, setAttributes] = useState<DataAttribute[]>([])
  const [attributesLoading, setAttributesLoading] = useState(false)
  const [selectedAttributeId, setSelectedAttributeId] = useState('')
  const [protectionMaskingMethod, setProtectionMaskingMethod] = useState('none')
  const [protectionEncryptionRequired, setProtectionEncryptionRequired] = useState(false)
  const [protectionEncryptionKeyId, setProtectionEncryptionKeyId] = useState('')
  const [encryptionKeys, setEncryptionKeys] = useState<Array<{ id: string; keyName: string; keyScope: string; workspaceId: string | null; isActive: boolean }>>([])
  const [encryptionKeysLoading, setEncryptionKeysLoading] = useState(false)
  const [definitionQuery, setDefinitionQuery] = useState('')
  const [definitionType, setDefinitionType] = useState('')
  const [definitions, setDefinitions] = useState<RegistryDefinition[]>([])
  const [definitionsLoading, setDefinitionsLoading] = useState(false)
  const [referenceDomainQuery, setReferenceDomainQuery] = useState('')
  const [referenceDomains, setReferenceDomains] = useState<RegistryDefinition[]>([])
  const [referenceDomainsLoading, setReferenceDomainsLoading] = useState(false)
  const [referenceDomainsError, setReferenceDomainsError] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [definitionDetailsById, setDefinitionDetailsById] = useState<Record<string, RegistryDefinition>>({})
  const [initialTargetApplied, setInitialTargetApplied] = useState(false)
  const [initialTarget] = useState<DefinitionMappingTarget | null>(() => {
    try {
      const raw = sessionStorage.getItem(DEFINITION_MAPPING_TARGET_STORAGE_KEY)
      if (!raw) {
        return null
      }
      const parsed = JSON.parse(raw) as Partial<DefinitionMappingTarget>
      if (!parsed.datasetId || !parsed.objectId || !parsed.versionId) {
        return null
      }
      return {
        productId: parsed.productId ? String(parsed.productId) : undefined,
        datasetId: String(parsed.datasetId),
        objectId: String(parsed.objectId),
        versionId: String(parsed.versionId),
        attributeId: parsed.attributeId ? String(parsed.attributeId) : undefined,
      }
    } catch {
      return null
    }
  })
  const [pendingInitialAttributeId, setPendingInitialAttributeId] = useState<string | null>(initialTarget?.attributeId || null)
  const [selectedDraftAttributeIds, setSelectedDraftAttributeIds] = useState<string[]>([])
  const [definitionTaskInput, setDefinitionTaskInput] = useState('')
  const [definitionTaskPolicies, setDefinitionTaskPolicies] = useState('')
  const [definitionTaskFeedback, setDefinitionTaskFeedback] = useState('')
  const [boardApprovalStatus, setBoardApprovalStatus] = useState('pending')
  const [boardApprovalNotes, setBoardApprovalNotes] = useState('')
  const [definitionTaskRequestId, setDefinitionTaskRequestId] = useState<string | null>(null)
  const [definitionTaskEventsUrl, setDefinitionTaskEventsUrl] = useState<string | null>(null)
  const [definitionTask, setDefinitionTask] = useState<DataDefinitionTaskStatus | null>(null)
  const [recentDefinitionTasks, setRecentDefinitionTasks] = useState<DataDefinitionTaskStatus[]>([])
  const [recentDefinitionTasksLoading, setRecentDefinitionTasksLoading] = useState(false)
  const [definitionTaskSubmitting, setDefinitionTaskSubmitting] = useState(false)
  const [definitionTaskUpdating, setDefinitionTaskUpdating] = useState(false)

  useEffect(() => {
    try {
      sessionStorage.removeItem(DEFINITION_MAPPING_TARGET_STORAGE_KEY)
    } catch {
      // ignore storage removal failures
    }
  }, [])

  useEffect(() => {
    const syncToken = () => setAuthToken(getAuthToken())
    syncToken()
    window.addEventListener('storage', syncToken)
    window.addEventListener('dq-auth-token-changed', syncToken)
    return () => {
      window.removeEventListener('storage', syncToken)
      window.removeEventListener('dq-auth-token-changed', syncToken)
    }
  }, [])

  const authHeaders = useMemo<Record<string, string>>(() => {
    const headers: Record<string, string> = {}
    if (authToken) {
      headers.Authorization = `Bearer ${authToken}`
    }
    return headers
  }, [authToken])

  const canManageEncryptionRegistry = auth.hasScope('dq:config:manage')

  useEffect(() => {
    if (!canManageEncryptionRegistry) {
      setEncryptionKeys([])
      setEncryptionKeysLoading(false)
      return
    }

    let cancelled = false
    const loadEncryptionKeys = async () => {
      setEncryptionKeysLoading(true)
      try {
        const systemApiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(`${systemApiBase}/encryption-keys`, {
          headers: {
            ...authHeaders,
          },
        })
        if (!response.ok) {
          throw new Error(`Unable to load encryption keys (${response.status})`)
        }
        const payload = snakeToCamel<Array<Record<string, unknown>>>(await response.json())
        if (cancelled) {
          return
        }
        setEncryptionKeys(payload.map((entry) => ({
          id: String(entry.id || ''),
          keyName: String(entry.keyName || ''),
          keyScope: String(entry.keyScope || ''),
          workspaceId: entry.workspaceId ? String(entry.workspaceId) : null,
          isActive: Boolean(entry.isActive),
        })))
      } catch {
        if (!cancelled) {
          setEncryptionKeys([])
        }
      } finally {
        if (!cancelled) {
          setEncryptionKeysLoading(false)
        }
      }
    }

    void loadEncryptionKeys()

    return () => {
      cancelled = true
    }
  }, [authHeaders, auth.hasScope, canManageEncryptionRegistry, settings.applicationSettings?.apiBaseUrl])

  const selectedProduct = useMemo<DataProduct | null>(
    () => filteredProducts.find((product) => product.id === selectedProductId) || null,
    [filteredProducts, selectedProductId]
  )
  const selectedDataset = useMemo<DataSet | null>(
    () => selectedProduct?.datasets?.find((dataset) => dataset.id === selectedDatasetId)
      || standaloneDatasets.find((dataset) => dataset.id === selectedDatasetId)
      || null,
    [selectedProduct, selectedDatasetId, standaloneDatasets]
  )
  const selectedObject = useMemo<DataObject | null>(
    () => selectedDataset?.dataObjects?.find((dataObject) => dataObject.id === selectedObjectId) || null,
    [selectedDataset, selectedObjectId]
  )
  const selectedVersion = useMemo<DataObjectVersion | null>(
    () => selectedObject?.versions?.find((version) => version.id === selectedVersionId) || null,
    [selectedObject, selectedVersionId]
  )
  const selectedAttribute = useMemo<DataAttribute | null>(
    () => attributes.find((attribute) => attribute.id === selectedAttributeId) || null,
    [attributes, selectedAttributeId]
  )
  const selectedDraftAttributes = useMemo<DataAttribute[]>(
    () => selectedDraftAttributeIds
      .map((attributeId) => attributes.find((attribute) => attribute.id === attributeId) || null)
      .filter((attribute): attribute is DataAttribute => attribute !== null),
    [attributes, selectedDraftAttributeIds]
  )
  const definitionTaskResult = definitionTask?.result || null
  const generatedDefinitions = definitionTaskResult?.registryContract?.definitions || []
  const activeWorkspaceId = useMemo(
    () => String(auth.currentWorkspaceId || '').trim(),
    [auth.currentWorkspaceId]
  )

  useEffect(() => {
    setProtectionMaskingMethod(selectedAttribute?.maskingMethod || 'none')
    setProtectionEncryptionRequired(Boolean(selectedAttribute?.encryptionRequired))
    setProtectionEncryptionKeyId(selectedAttribute?.encryptionKeyId || '')
  }, [selectedAttribute?.encryptionKeyId, selectedAttribute?.encryptionRequired, selectedAttribute?.maskingMethod])

  const currentDefinitionBindingCount = useMemo(
    () => (selectedAttribute?.definitionId ? attributes.filter((attribute) => attribute.definitionId === selectedAttribute.definitionId).length : 0),
    [attributes, selectedAttribute?.definitionId]
  )
  const datasetOptions = useMemo<DataSet[]>(
    () => selectedProduct?.datasets || standaloneDatasets,
    [selectedProduct, standaloneDatasets]
  )
  const productSelectOptions = useMemo(
    () => filteredProducts.map((product) => ({ value: product.id, label: product.name })),
    [filteredProducts]
  )
  const datasetSelectOptions = useMemo(
    () => datasetOptions.map((dataset) => ({ value: dataset.id, label: dataset.name })),
    [datasetOptions]
  )
  const objectSelectOptions = useMemo(
    () => (selectedDataset?.dataObjects || []).map((dataObject) => ({ value: dataObject.id, label: dataObject.name })),
    [selectedDataset]
  )
  const versionSelectOptions = useMemo(
    () => (selectedObject?.versions || []).map((version) => ({ value: version.id, label: `v${version.version}` })),
    [selectedObject]
  )

  useEffect(() => {
    if (!initialTarget || initialTargetApplied) {
      return
    }

    let cancelled = false

    const applyInitialTarget = async () => {
      setSelectedProductId(initialTarget.productId || '')
      setSelectedDatasetId(initialTarget.datasetId)
      setSelectedObjectId(initialTarget.objectId)
      setSelectedVersionId(initialTarget.versionId)
      setPendingInitialAttributeId(initialTarget.attributeId || null)

      if (initialTarget.productId) {
        await loadDatasets(initialTarget.productId)
      } else {
        selectProduct(null)
      }
      await loadDataObjects(initialTarget.datasetId)
      await loadVersions(initialTarget.objectId)

      if (cancelled) {
        return
      }

      const product = initialTarget.productId
        ? filteredProducts.find((item) => item.id === initialTarget.productId) || state.selectedProduct
        : null
      const dataset = (product?.datasets || standaloneDatasets).find((item) => item.id === initialTarget.datasetId)
        || state.selectedDataset
        || null
      const dataObject = dataset?.dataObjects?.find((item) => item.id === initialTarget.objectId)
        || state.selectedDataObject
        || null
      const version = dataObject?.versions?.find((item) => item.id === initialTarget.versionId)
        || state.selectedVersion
        || null

      selectProduct(product)
      selectDataset(dataset)
      selectDataObject(dataObject)
      selectVersion(version)
      setStatusMessage('Opened from Data Browser with the selected version and attribute focused.')
      setInitialTargetApplied(true)
    }

    void applyInitialTarget()
    return () => {
      cancelled = true
    }
  }, [filteredProducts, initialTarget, initialTargetApplied, loadDataObjects, loadDatasets, loadVersions, selectDataObject, selectDataset, selectProduct, selectVersion, standaloneDatasets, state.selectedDataObject, state.selectedDataset, state.selectedProduct, state.selectedVersion])

  const fetchAttributes = useCallback(async (versionId: string) => {
    setAttributesLoading(true)
    setErrorMessage(null)
    try {
      const response = await fetch(`${apiBase}/attributes-catalog?versionId=${encodeURIComponent(versionId)}`, {
        headers: authHeaders,
      })
      if (!response.ok) {
        throw new Error('Failed to load attribute mappings')
      }
      const payload = snakeToCamel<any>(await response.json())
      const nextAttributes: DataAttribute[] = Array.isArray(payload?.data)
        ? payload.data.map((item: Record<string, unknown>) => toAttribute(item))
        : []
      setAttributes(nextAttributes)
      setSelectedAttributeId((current) => {
        if (pendingInitialAttributeId && nextAttributes.some((attribute: DataAttribute) => attribute.id === pendingInitialAttributeId)) {
          return pendingInitialAttributeId
        }
        if (current && nextAttributes.some((attribute: DataAttribute) => attribute.id === current)) {
          return current
        }
        return nextAttributes[0]?.id || ''
      })
      if (pendingInitialAttributeId) {
        setPendingInitialAttributeId(null)
      }
    } catch (error) {
      setAttributes([])
      setSelectedAttributeId('')
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load attribute mappings')
    } finally {
      setAttributesLoading(false)
    }
  }, [apiBase, authHeaders, pendingInitialAttributeId])

  useEffect(() => {
    if (!definitionTaskRequestId) {
      setDefinitionTaskEventsUrl(null)
    }
  }, [definitionTaskRequestId])

  useEffect(() => {
    if (!selectedVersionId) {
      setAttributes([])
      setSelectedAttributeId('')
      setSelectedDraftAttributeIds([])
      setDefinitionTaskRequestId(null)
      setDefinitionTask(null)
      return
    }
    void fetchAttributes(selectedVersionId)
  }, [fetchAttributes, selectedVersionId])

  useEffect(() => {
    setSelectedDraftAttributeIds((current) => current.filter((attributeId) => attributes.some((attribute) => attribute.id === attributeId)))
  }, [attributes])

  useEffect(() => {
    if (!selectedAttribute?.definitionId || definitionDetailsById[selectedAttribute.definitionId]) {
      return
    }

    let cancelled = false
    const loadDefinition = async () => {
      try {
        const response = await fetch(
          `${apiBase}/registry/definitions/${encodeURIComponent(selectedAttribute.definitionId || '')}`,
          { headers: authHeaders }
        )
        if (!response.ok) {
          return
        }
        const payload = toDefinition(snakeToCamel<Record<string, unknown>>(await response.json()))
        if (!cancelled) {
          setDefinitionDetailsById((current) => ({ ...current, [payload.definitionId]: payload }))
        }
      } catch {
        return
      }
    }

    void loadDefinition()
    return () => {
      cancelled = true
    }
  }, [apiBase, authHeaders, definitionDetailsById, selectedAttribute?.definitionId])

  useEffect(() => {
    const handle = window.setTimeout(async () => {
      if (!selectedAttributeId) {
        setDefinitions([])
        return
      }
      setDefinitionsLoading(true)
      setErrorMessage(null)
      try {
        const params = new URLSearchParams({ limit: '20' })
        const normalizedQuery = definitionQuery.trim() || selectedAttribute?.name || ''
        if (normalizedQuery) {
          params.set('query', normalizedQuery)
        }
        if (definitionType.trim()) {
          params.set('definition_type', definitionType.trim())
        }
        const response = await fetch(`${apiBase}/registry/definitions?${params.toString()}`, {
          headers: authHeaders,
        })
        if (!response.ok) {
          throw new Error('Failed to search registry definitions')
        }
        const payload = snakeToCamel<Record<string, unknown>[]>(await response.json())
        const nextDefinitions = Array.isArray(payload)
          ? payload.map((item) => toDefinition(item))
          : []
        setDefinitions(nextDefinitions)
        setDefinitionDetailsById((current) => {
          const next = { ...current }
          nextDefinitions.forEach((definition) => {
            next[definition.definitionId] = definition
          })
          return next
        })
      } catch (error) {
        setDefinitions([])
        setErrorMessage(error instanceof Error ? error.message : 'Failed to search registry definitions')
      } finally {
        setDefinitionsLoading(false)
      }
    }, 250)

    return () => window.clearTimeout(handle)
  }, [apiBase, authHeaders, definitionQuery, definitionType, selectedAttribute?.name, selectedAttributeId])

  const handleProductChange = useCallback(async (nextProductId: string) => {
    setSelectedProductId(nextProductId)
    setSelectedDatasetId('')
    setSelectedObjectId('')
    setSelectedVersionId('')
    setAttributes([])
    setSelectedAttributeId('')
    setSelectedDraftAttributeIds([])
    setDefinitionTaskRequestId(null)
    setDefinitionTask(null)

    const product = filteredProducts.find((item) => item.id === nextProductId) || null
    selectProduct(product)
    selectDataset(null)
    selectDataObject(null)
    selectVersion(null)
    if (product) {
      await loadDatasets(product.id)
    }
  }, [filteredProducts, loadDatasets, selectDataObject, selectDataset, selectProduct, selectVersion])

  const handleDatasetChange = useCallback(async (nextDatasetId: string) => {
    setSelectedDatasetId(nextDatasetId)
    setSelectedObjectId('')
    setSelectedVersionId('')
    setAttributes([])
    setSelectedAttributeId('')
    setSelectedDraftAttributeIds([])
    setDefinitionTaskRequestId(null)
    setDefinitionTask(null)

    const dataset = selectedProduct?.datasets?.find((item) => item.id === nextDatasetId)
      || standaloneDatasets.find((item) => item.id === nextDatasetId)
      || null
    selectDataset(dataset)
    selectDataObject(null)
    selectVersion(null)
    if (dataset) {
      await loadDataObjects(dataset.id)
    }
  }, [loadDataObjects, selectDataObject, selectDataset, selectVersion, selectedProduct, standaloneDatasets])

  const handleObjectChange = useCallback(async (nextObjectId: string) => {
    setSelectedObjectId(nextObjectId)
    setSelectedVersionId('')
    setAttributes([])
    setSelectedAttributeId('')
    setSelectedDraftAttributeIds([])
    setDefinitionTaskRequestId(null)
    setDefinitionTask(null)

    const dataObject = selectedDataset?.dataObjects?.find((item) => item.id === nextObjectId) || null
    selectDataObject(dataObject)
    selectVersion(null)
    if (dataObject) {
      await loadVersions(dataObject.id)
    }
  }, [loadVersions, selectDataObject, selectVersion, selectedDataset])

  const handleVersionChange = useCallback((nextVersionId: string) => {
    setSelectedVersionId(nextVersionId)
    setSelectedDraftAttributeIds([])
    setDefinitionTaskRequestId(null)
    setDefinitionTask(null)
    const version = selectedObject?.versions?.find((item) => item.id === nextVersionId) || null
    selectVersion(version)
  }, [selectVersion, selectedObject])

  const loadDefinitionTaskStatus = useCallback(async (requestId: string) => {
    const response = await fetch(`${apiBase}/data-definition-tasks/requests/${encodeURIComponent(requestId)}/status`, {
      headers: authHeaders,
    })
    const rawPayload = await response.json().catch(() => null)
    const normalizedPayload = snakeToCamel<DataDefinitionTaskStatusResponse | Record<string, any>>(rawPayload)
    if (!response.ok) {
      throw new Error(String((normalizedPayload as Record<string, any>)?.detail?.message || (normalizedPayload as Record<string, any>)?.message || 'Failed to load data-definition task status'))
    }
    const taskRequest = (normalizedPayload as DataDefinitionTaskStatusResponse).request
    setDefinitionTask(taskRequest)
    return taskRequest
  }, [apiBase, authHeaders])

  const fetchWorkspaceDefinitionTaskHistory = useCallback(async (limit = 20) => {
    if (!activeWorkspaceId) {
      return [] as DataDefinitionTaskStatus[]
    }

    const params = new URLSearchParams({ limit: String(limit) })
    params.set('workspace_id', activeWorkspaceId)

    const response = await fetch(`${apiBase}/data-definition-tasks/requests?${params.toString()}`, {
      headers: authHeaders,
    })
    const rawPayload = await response.json().catch(() => null)
    const normalizedPayload = snakeToCamel<DataDefinitionTaskHistoryResponse | Record<string, any>>(rawPayload)

    if (!response.ok) {
      throw new Error(String((normalizedPayload as Record<string, any>)?.detail?.message || (normalizedPayload as Record<string, any>)?.message || 'Failed to load data-definition task history'))
    }

    return Array.isArray((normalizedPayload as DataDefinitionTaskHistoryResponse).requests)
      ? (normalizedPayload as DataDefinitionTaskHistoryResponse).requests
      : []
  }, [activeWorkspaceId, apiBase, authHeaders])

  const loadLatestDefinitionTaskForCurrentWorkspace = useCallback(async () => {
    const requests = await fetchWorkspaceDefinitionTaskHistory(20)
    const latestRequest = requests[0] || null
    if (!latestRequest) {
      return null
    }

    setDefinitionTaskRequestId(latestRequest.requestId)
    setDefinitionTask(latestRequest)
    if (latestRequest.status === 'pending' || latestRequest.status === 'started') {
      setDefinitionTaskEventsUrl(resolveTaskEventsUrl(apiBase, buildDataDefinitionTaskEventsPath(latestRequest.requestId)))
      setStatusMessage('Resumed the latest in-progress data-definition task for the current workspace.')
    } else {
      setDefinitionTaskEventsUrl(null)
      setStatusMessage('Loaded the latest data-definition task result for the current workspace.')
    }

    return latestRequest
  }, [apiBase, fetchWorkspaceDefinitionTaskHistory])

  useEffect(() => {
    if (!activeWorkspaceId) {
      setRecentDefinitionTasks([])
      setRecentDefinitionTasksLoading(false)
      return
    }

    let cancelled = false
    const loadRecent = async () => {
      setRecentDefinitionTasksLoading(true)
      try {
        const requests = await fetchWorkspaceDefinitionTaskHistory(10)
        if (!cancelled) {
          setRecentDefinitionTasks(requests)
        }
      } catch (error) {
        if (!cancelled) {
          setRecentDefinitionTasks([])
          setErrorMessage(error instanceof Error ? error.message : 'Failed to load data-definition task history')
        }
      } finally {
        if (!cancelled) {
          setRecentDefinitionTasksLoading(false)
        }
      }
    }

    void loadRecent()
    return () => {
      cancelled = true
    }
  }, [activeWorkspaceId, definitionTaskRequestId, fetchWorkspaceDefinitionTaskHistory])

  useEffect(() => {
    if (!selectedVersionId || definitionTaskRequestId || !activeWorkspaceId) {
      return
    }

    let cancelled = false
    const restoreTask = async () => {
      try {
        const restoredTask = await loadLatestDefinitionTaskForCurrentWorkspace()
        if (!cancelled && restoredTask && selectedDraftAttributeIds.length === 0) {
          setSelectedDraftAttributeIds(restoredTask.selectedAttributeIds || [])
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : 'Failed to restore latest data-definition task')
        }
      }
    }

    void restoreTask()
    return () => {
      cancelled = true
    }
  }, [activeWorkspaceId, definitionTaskRequestId, loadLatestDefinitionTaskForCurrentWorkspace, selectedDraftAttributeIds.length, selectedVersionId])

  useEffect(() => {
    if (!definitionTaskRequestId || !definitionTaskEventsUrl) {
      return
    }

    let cancelled = false
    const abortController = new AbortController()

    const subscribe = async () => {
      try {
        const response = await fetch(definitionTaskEventsUrl, {
          headers: {
            Accept: 'text/event-stream',
            ...authHeaders,
          },
          signal: abortController.signal,
        })
        if (!response.ok) {
          const rawPayload = await response.json().catch(() => null)
          const normalizedPayload = snakeToCamel<Record<string, any>>(rawPayload)
          throw new Error(String(normalizedPayload?.detail?.message || normalizedPayload?.message || 'Failed to subscribe to data-definition task events'))
        }
        if (!response.body) {
          throw new Error('Data-definition task event stream is unavailable.')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (!cancelled) {
          const { value, done } = await reader.read()
          if (done) {
            break
          }
          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split(/\r?\n\r?\n/)
          buffer = frames.pop() || ''
          for (const frame of frames) {
            const eventPayload = parseDataDefinitionTaskEventFrame(frame)
            if (!eventPayload?.request) {
              continue
            }
            setDefinitionTask(eventPayload.request)
            if (eventPayload.request.status === 'completed') {
              setStatusMessage('Data-definition task completed.')
              return
            }
            if (eventPayload.request.status === 'failed') {
              setErrorMessage(eventPayload.request.errorMessage || 'Data-definition task failed.')
              return
            }
          }
        }
      } catch (error) {
        if (!cancelled && !(error instanceof DOMException && error.name === 'AbortError')) {
          setErrorMessage(error instanceof Error ? error.message : 'Failed to subscribe to data-definition task events')
        }
      }
    }

    void subscribe()
    return () => {
      cancelled = true
      abortController.abort()
    }
  }, [apiBase, authHeaders, definitionTaskEventsUrl, definitionTaskRequestId, loadDefinitionTaskStatus])

  const addSelectedAttributeToDraft = useCallback(() => {
    if (!selectedAttribute) {
      return
    }
    setSelectedDraftAttributeIds((current) => current.includes(selectedAttribute.id) ? current : [...current, selectedAttribute.id])
  }, [selectedAttribute])

  const useAllAttributesForDraft = useCallback(() => {
    setSelectedDraftAttributeIds(attributes.map((attribute) => attribute.id))
  }, [attributes])

  const removeDraftAttribute = useCallback((attributeId: string) => {
    setSelectedDraftAttributeIds((current) => current.filter((currentAttributeId) => currentAttributeId !== attributeId))
  }, [])

  const submitDataDefinitionTask = useCallback(async () => {
    if (!selectedVersion) {
      setErrorMessage('Select a version before generating data definitions.')
      return
    }
    if (selectedDraftAttributeIds.length === 0) {
      setErrorMessage('Add at least one attribute to the draft scope before generating data definitions.')
      return
    }

    const currentWorkspaceId = selectedProduct?.workspaceId || selectedDataset?.workspaceId || ''
    if (!currentWorkspaceId) {
      setErrorMessage('The selected catalog context does not expose a workspace id for the data-definition task.')
      return
    }

    setDefinitionTaskSubmitting(true)
    setStatusMessage(null)
    setErrorMessage(null)
    try {
      const response = await fetch(`${apiBase}/data-definition-tasks`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders,
        },
        body: JSON.stringify(camelToSnake({
          currentWorkspaceId,
          versionId: selectedVersion.id,
          selectedAttributeIds: selectedDraftAttributeIds,
          userInput: definitionTaskInput.trim() || undefined,
          policies: toTextLines(definitionTaskPolicies),
          feedbackItems: definitionTaskFeedback.trim()
            ? [{
                sourceRole: 'data_steward',
                comment: definitionTaskFeedback.trim(),
                authorName: auth.user?.name || auth.user?.email || undefined,
                targetIds: selectedDraftAttributeIds,
              }]
            : [],
          boardApproval: boardApprovalStatus !== 'pending' || boardApprovalNotes.trim()
            ? {
                boardName: 'Data Definition Board',
                status: boardApprovalStatus,
                approverName: auth.user?.name || auth.user?.email || undefined,
                approvalNotes: boardApprovalNotes.trim() || undefined,
                approvedAt: boardApprovalStatus === 'approved' ? new Date().toISOString() : undefined,
              }
            : undefined,
          stewardName: auth.user?.name || auth.user?.email || undefined,
          boardName: 'Data Definition Board',
          domainName: selectedProduct?.name || undefined,
          sourceSystem: selectedObject?.name || selectedDataset?.name || undefined,
        })),
      })
      const rawPayload = await response.json().catch(() => null)
      const normalizedPayload = snakeToCamel<DataDefinitionTaskCreateResponse | Record<string, any>>(rawPayload)
      if (!response.ok) {
        throw new Error(String((normalizedPayload as Record<string, any>)?.detail?.message || (normalizedPayload as Record<string, any>)?.message || 'Failed to queue data-definition task'))
      }
      const queuedTask = normalizedPayload as DataDefinitionTaskCreateResponse
      setDefinitionTaskRequestId(queuedTask.requestId)
      setDefinitionTaskEventsUrl(resolveTaskEventsUrl(apiBase, queuedTask.eventsUrl))
      setDefinitionTask(null)
      setStatusMessage(queuedTask.message)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to queue data-definition task')
    } finally {
      setDefinitionTaskSubmitting(false)
    }
  }, [apiBase, auth.user?.email, auth.user?.name, authHeaders, boardApprovalNotes, boardApprovalStatus, definitionTaskFeedback, definitionTaskInput, definitionTaskPolicies, selectedDataset?.name, selectedDataset?.workspaceId, selectedDraftAttributeIds, selectedObject?.name, selectedProduct?.name, selectedProduct?.workspaceId, selectedVersion])

  const captureBoardApproval = useCallback(async () => {
    if (!definitionTaskRequestId) {
      setErrorMessage('Generate a data-definition draft before capturing board approval.')
      return
    }

    setDefinitionTaskUpdating(true)
    setStatusMessage(null)
    setErrorMessage(null)
    try {
      const response = await fetch(`${apiBase}/data-definition-tasks/requests/${encodeURIComponent(definitionTaskRequestId)}/approval`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders,
        },
        body: JSON.stringify(camelToSnake({
          boardApproval: {
            boardName: 'Data Definition Board',
            status: boardApprovalStatus,
            approverName: auth.user?.name || auth.user?.email || undefined,
            approvalNotes: boardApprovalNotes.trim() || undefined,
            approvedAt: boardApprovalStatus === 'approved' ? new Date().toISOString() : undefined,
          },
        })),
      })
      const rawPayload = await response.json().catch(() => null)
      const normalizedPayload = snakeToCamel<DataDefinitionTaskStatusResponse | Record<string, any>>(rawPayload)
      if (!response.ok) {
        throw new Error(String((normalizedPayload as Record<string, any>)?.detail?.message || (normalizedPayload as Record<string, any>)?.message || 'Failed to capture board approval'))
      }
      const updatedTask = (normalizedPayload as DataDefinitionTaskStatusResponse).request
      setDefinitionTask(updatedTask)
      const importResult = updatedTask.result?.openmetadataImportResult
      if (boardApprovalStatus === 'approved' && importResult) {
        setStatusMessage(`Approved and imported ${importResult.definitionCount || 0} data definitions into ${importResult.glossary?.fullyQualifiedName || 'OpenMetadata'}.`)
      } else {
        setStatusMessage(`Captured ${boardApprovalStatus} board decision for the active data-definition draft.`)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to capture board approval')
    } finally {
      setDefinitionTaskUpdating(false)
    }
  }, [apiBase, auth.user?.email, auth.user?.name, authHeaders, boardApprovalNotes, boardApprovalStatus, definitionTaskRequestId])

  const importGeneratedDefinitions = useCallback(async () => {
    if (!definitionTaskRequestId) {
      setErrorMessage('Generate a data-definition draft before importing it into OpenMetadata.')
      return
    }

    setDefinitionTaskUpdating(true)
    setStatusMessage(null)
    setErrorMessage(null)
    try {
      const response = await fetch(`${apiBase}/data-definition-tasks/requests/${encodeURIComponent(definitionTaskRequestId)}/openmetadata-sync`, {
        method: 'POST',
        headers: authHeaders,
      })
      const rawPayload = await response.json().catch(() => null)
      const normalizedPayload = snakeToCamel<DataDefinitionTaskImportResponse | Record<string, any>>(rawPayload)
      if (!response.ok) {
        throw new Error(String((normalizedPayload as Record<string, any>)?.detail?.message || (normalizedPayload as Record<string, any>)?.message || 'Failed to import generated data definitions'))
      }
      setStatusMessage((normalizedPayload as DataDefinitionTaskImportResponse).message)
      await loadDefinitionTaskStatus(definitionTaskRequestId)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to import generated data definitions')
    } finally {
      setDefinitionTaskUpdating(false)
    }
  }, [apiBase, authHeaders, definitionTaskRequestId, loadDefinitionTaskStatus])

  const saveMapping = useCallback(async (mappingState: 'mapped' | 'unmapped', definitionId?: string) => {
    if (!selectedAttribute || !selectedVersion) {
      return
    }

    setIsSaving(true)
    setStatusMessage(null)
    setErrorMessage(null)
    try {
      const response = await fetch(`${apiBase}/attribute-definition-mappings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders,
        },
        body: JSON.stringify({
          attribute_id: selectedAttribute.id,
          definition_id: mappingState === 'mapped' ? definitionId : null,
          mapping_state: mappingState,
          mapped_by: auth.user?.email || auth.user?.name || undefined,
        }),
      })
      if (!response.ok) {
        const errorPayload = snakeToCamel<Record<string, any>>(await response.json())
        throw new Error(String(errorPayload?.detail?.message || errorPayload?.message || 'Failed to save mapping'))
      }
      setStatusMessage(
        mappingState === 'mapped'
          ? `Mapped ${selectedAttribute.name} to ${definitionId}`
          : `Cleared the definition link for ${selectedAttribute.name} on version ${selectedVersion.version}`
      )
      await fetchAttributes(selectedVersion.id)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to save mapping')
    } finally {
      setIsSaving(false)
    }
  }, [apiBase, auth.user?.email, auth.user?.name, authHeaders, fetchAttributes, selectedAttribute, selectedVersion])

  const saveProtection = useCallback(async () => {
    if (!selectedAttribute) {
      return
    }

    if (!selectedVersion) {
      setErrorMessage('Select a version before updating protection settings.')
      return
    }

    if (protectionEncryptionRequired && !canManageEncryptionRegistry) {
      setErrorMessage('Encryption settings require app-admin access to the key registry.')
      return
    }

    if (protectionEncryptionRequired && !protectionEncryptionKeyId) {
      setErrorMessage('Choose an encryption key before enabling encryption.')
      return
    }

    setIsSaving(true)
    setStatusMessage(null)
    setErrorMessage(null)
    try {
      const response = await fetch(`${apiBase}/attributes-catalog/${encodeURIComponent(selectedAttribute.id)}/protection`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders,
        },
        body: JSON.stringify({
          masking_method: protectionMaskingMethod,
          encryption_required: protectionEncryptionRequired,
          encryption_key_id: protectionEncryptionRequired ? protectionEncryptionKeyId : null,
        }),
      })
      if (!response.ok) {
        const errorPayload = snakeToCamel<Record<string, any>>(await response.json())
        throw new Error(String(errorPayload?.detail?.message || errorPayload?.detail || errorPayload?.message || 'Failed to save protection settings'))
      }
      setStatusMessage(`Updated protection settings for ${selectedAttribute.name}`)
      await fetchAttributes(selectedVersion.id)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to save protection settings')
    } finally {
      setIsSaving(false)
    }
  }, [apiBase, authHeaders, canManageEncryptionRegistry, fetchAttributes, protectionEncryptionKeyId, protectionEncryptionRequired, protectionMaskingMethod, selectedAttribute, selectedVersion])

  const currentDefinition = selectedAttribute?.definitionId
    ? definitionDetailsById[selectedAttribute.definitionId]
    : undefined
  const currentDefinitionGlossaryLabel = currentDefinition?.glossaryName || currentDefinition?.glossaryId || 'n/a'
  const currentDefinitionSynonymsLabel = currentDefinition?.synonyms?.length ? currentDefinition.synonyms.join(', ') : 'n/a'
  const currentDefinitionParentLabel = currentDefinition?.parentDefinitionName || currentDefinition?.parentDefinitionId || 'n/a'
  const currentDefinitionChildrenLabel = currentDefinition?.childDefinitionNames?.length
    ? currentDefinition.childDefinitionNames.join(', ')
    : currentDefinition?.childDefinitionCount
      ? `${currentDefinition.childDefinitionCount} child term${currentDefinition.childDefinitionCount === 1 ? '' : 's'}`
      : 'n/a'
  const currentDefinitionAppliesToLabel = currentDefinition?.appliesTo?.length ? currentDefinition.appliesTo.join(', ') : 'n/a'
  const referenceDomainCount = referenceDomains.length
  const referenceLookupValueCount = useMemo(
    () => referenceDomains.reduce(
      (total, item) => total + (item.valueDomain?.allowedValues?.length || 0),
      0
    ),
    [referenceDomains]
  )

  useEffect(() => {
    if (activeCatalogView !== 'reference-data') {
      return
    }

    const handle = window.setTimeout(async () => {
      setReferenceDomainsLoading(true)
      setReferenceDomainsError(null)
      try {
        const params = new URLSearchParams({ limit: '20' })
        const normalizedQuery = referenceDomainQuery.trim()
        if (normalizedQuery) {
          params.set('query', normalizedQuery)
        }
        const response = await fetch(`${apiBase}/registry/reference-domains?${params.toString()}`, {
          headers: authHeaders,
        })
        if (!response.ok) {
          throw new Error('Failed to load reference data')
        }
        const payload = snakeToCamel<Record<string, unknown>[]>(await response.json())
        const nextReferenceDomains = Array.isArray(payload)
          ? payload.map((item) => toDefinition(item)).filter((item) => item.valueDomain?.allowedValues?.length)
          : []
        setReferenceDomains(nextReferenceDomains)
      } catch (error) {
        setReferenceDomains([])
        setReferenceDomainsError(error instanceof Error ? error.message : 'Failed to load reference data')
      } finally {
        setReferenceDomainsLoading(false)
      }
    }, 250)

    return () => window.clearTimeout(handle)
  }, [activeCatalogView, apiBase, authHeaders, referenceDomainQuery])

  return (
    <AppPageShell className="definition-mappings-page">
      <AppStack gap="lg">
        <AppPageHeader
          eyebrow="Data Catalog governance"
          title="Definition Mappings"
          description="Map registry Definitions to versioned attributes. New versions inherit the previous link until a steward overrides or clears it."
        />

        <AppPanel tone="muted" className="definition-mappings-status-card" bodyClassName="definition-mappings-status-card-content">
          {activeCatalogView === 'mappings' ? (
            <>
              <div>
                <span>Selected version</span>
                <strong>{selectedVersion ? `${selectedObject?.name || 'Object'} v${selectedVersion.version}` : 'None selected'}</strong>
              </div>
              <div>
                <span>Selected attribute</span>
                <strong>{selectedAttribute?.name || 'Choose an attribute'}</strong>
              </div>
            </>
          ) : (
            <>
              <div>
                <span>Reference domains</span>
                <strong>{referenceDomainCount} code list{referenceDomainCount === 1 ? '' : 's'}</strong>
              </div>
              <div>
                <span>Lookup values</span>
                <strong>{referenceLookupValueCount}</strong>
              </div>
            </>
          )}
        </AppPanel>

        <AppToolbar className="definition-mappings-tabs" role="tablist" aria-label="Catalog governance views" align="start">
          <button
            type="button"
            className={`definition-mappings-tab${activeCatalogView === 'mappings' ? ' active' : ''}`}
            aria-selected={activeCatalogView === 'mappings'}
            onClick={() => setActiveCatalogView('mappings')}
          >
            Definition Mappings
          </button>
          <button
            type="button"
            className={`definition-mappings-tab${activeCatalogView === 'reference-data' ? ' active' : ''}`}
            aria-selected={activeCatalogView === 'reference-data'}
            onClick={() => setActiveCatalogView('reference-data')}
          >
            Reference Data
          </button>
        </AppToolbar>

        {activeCatalogView === 'mappings' ? (
          <>
            <AppPanel className="definition-mappings-selectors-panel" bodyClassName="definition-mappings-selectors">
            <AppSelect
              id="definition-mappings-product"
              label="Product"
              value={selectedProductId}
              onChange={(value) => void handleProductChange(value)}
              options={productSelectOptions}
              placeholderLabel="Select product"
            />
            <AppSelect
              id="definition-mappings-dataset"
              label="Dataset"
              value={selectedDatasetId}
              onChange={(value) => void handleDatasetChange(value)}
              options={datasetSelectOptions}
              placeholderLabel="Select dataset"
              disabled={!selectedProduct && standaloneDatasets.length === 0}
            />
            <AppSelect
              id="definition-mappings-object"
              label="Data object"
              value={selectedObjectId}
              onChange={(value) => void handleObjectChange(value)}
              options={objectSelectOptions}
              placeholderLabel="Select data object"
              disabled={!selectedDataset}
            />
            <AppSelect
              id="definition-mappings-version"
              label="Version"
              value={selectedVersionId}
              onChange={handleVersionChange}
              options={versionSelectOptions}
              placeholderLabel="Select version"
              disabled={!selectedObject}
            />
            </AppPanel>

            {(statusMessage || errorMessage) && (
              <StatusBanner
                variant={errorMessage ? 'error' : 'success'}
                message={errorMessage || statusMessage || ''}
                onDismiss={() => {
                  setErrorMessage(null)
                  setStatusMessage(null)
                }}
                className="definition-mappings-banner"
              />
            )}

            <div className="definition-mappings-layout">
              <AppPanel
                title="Version attributes"
                description="Choose the attribute you want to govern for this version."
                actions={attributesLoading ? <span className="definition-mappings-meta">Refreshing…</span> : undefined}
                className="definition-mappings-attributes-panel"
                bodyClassName="definition-mappings-attributes-table"
              >
                <div className="definition-mappings-table-head">
                  <span>Attribute</span>
                  <span>Status</span>
                  <span>Definition</span>
                </div>
                {attributes.map((attribute) => (
                  <button
                    key={attribute.id}
                    type="button"
                    className={`definition-mappings-row${attribute.id === selectedAttributeId ? ' selected' : ''}`}
                    onClick={() => setSelectedAttributeId(attribute.id)}
                  >
                    <span>
                      <strong>{attribute.name}</strong>
                      <small>{attribute.type}{attribute.nullable ? ' • nullable' : ''}</small>
                    </span>
                    <span>
                      <AppBadge tone={getMappingStatusTone(attribute.definitionMappingStatus)}>
                        {MAPPING_STATUS_LABELS[attribute.definitionMappingStatus || 'unmapped']}
                      </AppBadge>
                    </span>
                    <span>{attribute.definitionId || 'No definition selected'}</span>
                  </button>
                ))}
                {!attributesLoading && attributes.length === 0 && (
                  <AppEmptyState
                    title="Select a version to inspect its attributes."
                    description="Choose a product, dataset, object, and version to load the version attributes."
                  />
                )}
              </AppPanel>

              <AppPanel
                title="Mapping workbench"
                description="Search governed Definitions, review the current link, and apply an explicit override for this version."
                className="definition-mappings-workbench-panel"
              >

              {selectedAttribute ? (
                <>
                  <div className="definition-mappings-attribute-card">
                    <div>
                      <span className="definition-mappings-card-label">Attribute</span>
                      <h3>{selectedAttribute.name}</h3>
                      <p>{selectedObject?.name || 'Data object'} • version {selectedVersion?.version || 'n/a'}</p>
                    </div>
                    <div className="definition-mappings-card-meta">
                      <AppBadge tone={getMappingStatusTone(selectedAttribute.definitionMappingStatus)}>
                        {MAPPING_STATUS_LABELS[selectedAttribute.definitionMappingStatus || 'unmapped']}
                      </AppBadge>
                      {selectedAttribute.definitionMappingVersionId && (
                        <small>Source version: {selectedAttribute.definitionMappingVersionId}</small>
                      )}
                    </div>
                  </div>

                  <div className="definition-mappings-current-definition">
                    <h3>Current effective definition</h3>
                    {selectedAttribute.definitionId ? (
                      <div className="definition-mappings-definition-card current">
                        <strong>{currentDefinition?.definitionName || selectedAttribute.definitionId}</strong>
                        <p>{currentDefinition?.businessDefinition || 'Definition details are loading or unavailable.'}</p>
                        <dl>
                          <div>
                            <dt>Definition ID</dt>
                            <dd>{selectedAttribute.definitionId}</dd>
                          </div>
                          <div>
                            <dt>Source</dt>
                            <dd>{MAPPING_STATUS_LABELS[selectedAttribute.definitionMappingStatus || 'unmapped']}</dd>
                          </div>
                          <div>
                            <dt>Steward</dt>
                            <dd>{currentDefinition?.owner || 'n/a'}</dd>
                          </div>
                          <div>
                            <dt>Glossary</dt>
                            <dd>{currentDefinitionGlossaryLabel}</dd>
                          </div>
                          <div>
                            <dt>Synonyms</dt>
                            <dd>{currentDefinitionSynonymsLabel}</dd>
                          </div>
                          <div>
                            <dt>Hierarchy</dt>
                            <dd>{[currentDefinitionParentLabel, currentDefinitionChildrenLabel].filter(Boolean).join(' • ')}</dd>
                          </div>
                          <div>
                            <dt>Applies to</dt>
                            <dd>{currentDefinitionAppliesToLabel}</dd>
                          </div>
                          <div>
                            <dt>Version bindings</dt>
                            <dd>{currentDefinitionBindingCount}</dd>
                          </div>
                        </dl>
                      </div>
                    ) : (
                      <AppEmptyState
                        title="This attribute does not currently resolve to a governed definition."
                        description="Map it to a governed definition or leave it unmapped for this version."
                      />
                    )}
                  </div>

                  <div className="definition-mappings-current-definition">
                    <h3>Protection policy</h3>
                    <div className="definition-mappings-definition-card current">
                      <dl>
                        <div>
                          <dt>Masking method</dt>
                          <dd>{selectedAttribute.maskingMethod || 'none'}</dd>
                        </div>
                        <div>
                          <dt>Encryption</dt>
                          <dd>{selectedAttribute.encryptionRequired ? 'required' : 'not required'}</dd>
                        </div>
                        <div>
                          <dt>Encryption key</dt>
                          <dd>{selectedAttribute.encryptionKeyId || 'n/a'}</dd>
                        </div>
                        <div>
                          <dt>Configured by</dt>
                          <dd>{selectedAttribute.protectionConfiguredBy || 'n/a'}</dd>
                        </div>
                        <div>
                          <dt>Updated at</dt>
                          <dd>{selectedAttribute.protectionUpdatedAt || 'n/a'}</dd>
                        </div>
                      </dl>

                      <div className="definition-mappings-search-controls">
                        <AppSelect
                          id="attribute-protection-masking-method"
                          label="Masking method"
                          value={protectionMaskingMethod}
                          onChange={(value) => setProtectionMaskingMethod(value)}
                          options={(settings.applicationSettings?.dataProtectionMaskingMethods || ['none', 'redact', 'partial', 'tokenize']).map((method) => ({
                            value: method,
                            label: method,
                          }))}
                          placeholderLabel="Select masking method"
                        />
                        <div className="definition-mappings-inline-toggle">
                          <label htmlFor="attribute-protection-encryption-required">
                            <input
                              id="attribute-protection-encryption-required"
                              type="checkbox"
                              checked={protectionEncryptionRequired}
                              onChange={(event) => setProtectionEncryptionRequired(event.target.checked)}
                              disabled={!canManageEncryptionRegistry}
                            />
                            Encryption required
                          </label>
                        </div>
                        {canManageEncryptionRegistry ? (
                          <AppSelect
                            id="attribute-protection-encryption-key"
                            label="Encryption key"
                            value={protectionEncryptionKeyId}
                            onChange={(value) => setProtectionEncryptionKeyId(value)}
                            options={encryptionKeys.map((key) => ({
                              value: key.id,
                              label: `${key.keyName} (${key.keyScope})`,
                            }))}
                            placeholderLabel={encryptionKeysLoading ? 'Loading keys…' : 'Select encryption key'}
                            disabled={!protectionEncryptionRequired || encryptionKeysLoading}
                          />
                        ) : (
                          <AppEmptyState
                            title="Encryption keys are managed from the app-admin key registry."
                            description="Use the registry management view to configure encryption keys before enabling encryption for this attribute."
                          />
                        )}
                      </div>

                      <div className="definition-mappings-actions">
                        <Button type="button" variant="primary" onClick={() => void saveProtection()} disabled={isSaving}>
                          Save protection
                        </Button>
                      </div>
                    </div>
                  </div>

                  <div className="definition-mappings-current-definition">
                    <h3>Data definition task</h3>
                    <div className="definition-mappings-definition-card current definition-mappings-task-card">
                      <div className="definition-mappings-task-summary">
                        <div>
                          <span className="definition-mappings-card-label">Draft scope</span>
                          <strong>{selectedDraftAttributes.length} attribute{selectedDraftAttributes.length === 1 ? '' : 's'} selected</strong>
                          <p>Generate or revise board-review-ready data definitions from the platform workflow using selected catalog attributes.</p>
                        </div>
                        <div className="definition-mappings-card-meta">
                          <AppBadge tone={getMappingStatusTone(definitionTask?.status)}>
                            {definitionTask ? `Task ${definitionTask.status}` : 'No active task'}
                          </AppBadge>
                          {definitionTask?.requestId && <small>Request: {definitionTask.requestId}</small>}
                        </div>
                      </div>

                      <div className="definition-mappings-task-chip-list">
                        {selectedDraftAttributes.map((attribute) => (
                          <span key={attribute.id} className="definition-mappings-task-chip">
                            {attribute.name}
                            <button type="button" onClick={() => removeDraftAttribute(attribute.id)} aria-label={`Remove ${attribute.name} from data-definition scope`}>
                              x
                            </button>
                          </span>
                        ))}
                        {selectedDraftAttributes.length === 0 && (
                          <AppEmptyState
                            title="Add one or more attributes to the draft scope."
                            description="Use the current attribute or select all version attributes before generating a draft."
                          />
                        )}
                      </div>

                      <div className="definition-mappings-actions definition-mappings-task-scope-actions">
                        <Button type="button" variant="secondary" onClick={addSelectedAttributeToDraft} disabled={!selectedAttribute}>
                          Add current attribute
                        </Button>
                        <Button type="button" variant="secondary" onClick={useAllAttributesForDraft} disabled={attributes.length === 0}>
                          Use all version attributes
                        </Button>
                        <Button type="button" variant="tertiary" onClick={() => setSelectedDraftAttributeIds([])} disabled={selectedDraftAttributeIds.length === 0}>
                          Clear draft scope
                        </Button>
                      </div>

                      <div className="definition-mappings-task-form">
                        <label className="definition-mappings-task-field" htmlFor="data-definition-user-input">
                          <span>Steward input</span>
                          <textarea
                            id="data-definition-user-input"
                            className="definition-mappings-textarea"
                            value={definitionTaskInput}
                            onChange={(event) => setDefinitionTaskInput(event.target.value)}
                            placeholder="Describe business meaning, BCBS239 obligations, ambiguity to resolve, or steward guidance."
                            rows={3}
                          />
                        </label>
                        <label className="definition-mappings-task-field" htmlFor="data-definition-policies">
                          <span>Policies and guardrails</span>
                          <textarea
                            id="data-definition-policies"
                            className="definition-mappings-textarea"
                            value={definitionTaskPolicies}
                            onChange={(event) => setDefinitionTaskPolicies(event.target.value)}
                            placeholder="One policy per line, for example: Use ISO 11179 naming"
                            rows={3}
                          />
                        </label>
                        <label className="definition-mappings-task-field" htmlFor="data-definition-feedback">
                          <span>Feedback for next draft</span>
                          <textarea
                            id="data-definition-feedback"
                            className="definition-mappings-textarea"
                            value={definitionTaskFeedback}
                            onChange={(event) => setDefinitionTaskFeedback(event.target.value)}
                            placeholder="Capture steward review comments before regenerating a revised draft."
                            rows={3}
                          />
                        </label>
                      </div>

                      <div className="definition-mappings-task-review-grid">
                        <AppSelect
                          id="data-definition-board-status"
                          label="Board approval status"
                          value={boardApprovalStatus}
                          onChange={(value) => setBoardApprovalStatus(value)}
                          options={[
                            { value: 'pending', label: 'Pending' },
                            { value: 'approved', label: 'Approved' },
                            { value: 'rejected', label: 'Rejected' },
                          ]}
                          placeholderLabel="Select approval status"
                        />
                        <label className="definition-mappings-task-field" htmlFor="data-definition-board-notes">
                          <span>Board notes</span>
                          <textarea
                            id="data-definition-board-notes"
                            className="definition-mappings-textarea"
                            value={boardApprovalNotes}
                            onChange={(event) => setBoardApprovalNotes(event.target.value)}
                            placeholder="Capture board decision notes or approval rationale."
                            rows={3}
                          />
                        </label>
                      </div>

                      <div className="definition-mappings-actions definition-mappings-task-actions">
                        <Button type="button" variant="primary" onClick={() => void submitDataDefinitionTask()} disabled={definitionTaskSubmitting || !selectedVersion}>
                          {generatedDefinitions.length > 0 ? 'Generate revised draft' : 'Generate draft'}
                        </Button>
                        <Button type="button" variant="secondary" onClick={() => void captureBoardApproval()} disabled={definitionTaskUpdating || !definitionTaskRequestId || definitionTask?.status !== 'completed'}>
                          Capture board approval
                        </Button>
                        <Button type="button" variant="secondary" onClick={() => void importGeneratedDefinitions()} disabled={definitionTaskUpdating || !definitionTaskRequestId || definitionTaskResult?.reviewStatus !== 'approved'}>
                          {definitionTaskResult?.openmetadataImportResult ? 'Re-sync OpenMetadata' : 'Import to OpenMetadata'}
                        </Button>
                      </div>

                      {definitionTask && (
                        <div className="definition-mappings-task-status">
                          <div>
                            <span className="definition-mappings-card-label">Review status</span>
                            <strong>{definitionTaskResult?.reviewStatus || definitionTask.status}</strong>
                          </div>
                          <div>
                            <span className="definition-mappings-card-label">Board packet</span>
                            <strong>{definitionTaskResult?.boardReviewPacket?.boardName || 'Data Definition Board'}</strong>
                          </div>
                          {definitionTask.errorMessage && <p>{definitionTask.errorMessage}</p>}
                          {definitionTaskResult?.boardReviewPacket?.reviewSummary && <p>{definitionTaskResult.boardReviewPacket.reviewSummary}</p>}
                          {definitionTaskResult?.openmetadataImportResult && (
                            <p>
                              Imported {definitionTaskResult.openmetadataImportResult.definitionCount || 0} definitions into {definitionTaskResult.openmetadataImportResult.glossary?.fullyQualifiedName || 'OpenMetadata'}.
                            </p>
                          )}
                        </div>
                      )}

                      <div className="definition-mappings-task-status">
                        <div>
                          <span className="definition-mappings-card-label">Recent tasks (current workspace)</span>
                          <strong>{activeWorkspaceId || 'No active workspace selected'}</strong>
                        </div>
                        {recentDefinitionTasksLoading ? (
                          <p>Loading recent tasks...</p>
                        ) : recentDefinitionTasks.length > 0 ? (
                          <div className="definition-mappings-task-list">
                            {recentDefinitionTasks.slice(0, 5).map((task) => (
                              <div key={task.requestId} className="definition-mappings-task-list-item">
                                {task.requestId} - {task.status} - by {task.requestedByEmail || task.requestedByUserId || 'unknown'}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p>No recent data-definition tasks were found for the current workspace.</p>
                        )}
                      </div>

                      {generatedDefinitions.length > 0 && (
                        <div className="definition-mappings-results">
                          <div className="definition-mappings-results-header">
                            <h3>Generated draft definitions</h3>
                            <span className="definition-mappings-meta">{generatedDefinitions.length} definition{generatedDefinitions.length === 1 ? '' : 's'}</span>
                          </div>
                          {generatedDefinitions.map((definition) => (
                            <div key={definition.definitionId} className="definition-mappings-definition-card">
                              <div>
                                <strong>{definition.definitionName}</strong>
                                <p>{definition.businessDefinition || 'No business definition supplied.'}</p>
                              </div>
                              <dl>
                                <div>
                                  <dt>Definition ID</dt>
                                  <dd>{definition.definitionId}</dd>
                                </div>
                                <div>
                                  <dt>Status</dt>
                                  <dd>{definition.status || definition.boardReviewStatus || 'draft'}</dd>
                                </div>
                                <div>
                                  <dt>Examples</dt>
                                  <dd>{definition.examples?.length ? definition.examples.join(', ') : 'n/a'}</dd>
                                </div>
                                <div>
                                  <dt>Constraints</dt>
                                  <dd>{definition.constraints?.length ? definition.constraints.join(', ') : 'n/a'}</dd>
                                </div>
                              </dl>
                              {definition.openQuestions?.length ? (
                                <div className="definition-mappings-task-list">
                                  {definition.openQuestions.map((question) => (
                                    <span key={question} className="definition-mappings-task-list-item">{question}</span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="definition-mappings-search-controls">
                    <AppInput
                      id="definition-mappings-search-query"
                      label="Search Definitions"
                      type="search"
                      value={definitionQuery}
                      onChange={(event: any) => setDefinitionQuery(getFieldValue(event))}
                      onInput={(event: any) => setDefinitionQuery(getFieldValue(event))}
                      placeholder={selectedAttribute.name}
                    />
                    <AppInput
                      id="definition-mappings-search-type"
                      label="Definition type"
                      type="text"
                      value={definitionType}
                      onChange={(event: any) => setDefinitionType(getFieldValue(event))}
                      onInput={(event: any) => setDefinitionType(getFieldValue(event))}
                      placeholder="attribute"
                    />
                  </div>

                  <div className="definition-mappings-results">
                    <div className="definition-mappings-results-header">
                      <h3>Candidate Definitions</h3>
                      {definitionsLoading && <span className="definition-mappings-meta">Searching…</span>}
                    </div>
                    {definitions.map((definition) => (
                      <div key={definition.definitionId} className="definition-mappings-definition-card">
                        <div>
                          <strong>{definition.definitionName}</strong>
                          <p>{definition.businessDefinition || 'No business definition supplied.'}</p>
                        </div>
                        <dl>
                          <div>
                            <dt>Definition ID</dt>
                            <dd>{definition.definitionId}</dd>
                          </div>
                          <div>
                            <dt>Object / Property</dt>
                            <dd>{[definition.objectClass, definition.property].filter(Boolean).join(' / ') || 'n/a'}</dd>
                          </div>
                          <div>
                            <dt>Glossary</dt>
                            <dd>{definition.glossaryName || definition.glossaryId || 'n/a'}</dd>
                          </div>
                          <div>
                            <dt>Synonyms</dt>
                            <dd>{definition.synonyms?.length ? definition.synonyms.join(', ') : 'n/a'}</dd>
                          </div>
                        </dl>
                        <Button
                          variant="secondary"
                          disabled={isSaving}
                          onClick={() => void saveMapping('mapped', definition.definitionId)}
                        >
                          Map to attribute
                        </Button>
                      </div>
                    ))}
                    {!definitionsLoading && definitions.length === 0 && (
                      <AppEmptyState
                        title="No registry Definitions matched this search."
                        description="Adjust the query or definition type to broaden the candidate set."
                      />
                    )}
                  </div>

                  <div className="definition-mappings-actions">
                    <Button
                      variant="tertiary"
                      destructive
                      disabled={isSaving}
                      onClick={() => void saveMapping('unmapped')}
                    >
                      Clear mapping for this version
                    </Button>
                  </div>
                </>
              ) : (
                <AppEmptyState
                  title="Select an attribute to review or override its governed definition link."
                  description="Choose a version attribute from the left panel to open the mapping workbench."
                />
              )}
            </AppPanel>
          </div>
        </>
      ) : (
        <section className="definition-mappings-reference-panel">
          {referenceDomainsError && (
            <StatusBanner
              variant="error"
              message={referenceDomainsError}
              onDismiss={() => setReferenceDomainsError(null)}
              className="definition-mappings-banner"
            />
          )}

          <div className="definition-mappings-panel-header">
            <div>
              <h2>Reference data</h2>
              <p>Browse governed code lists and reusable domains surfaced from OpenMetadata value-domain metadata.</p>
            </div>
            {referenceDomainsLoading && <span className="definition-mappings-meta">Refreshing…</span>}
          </div>

          <div className="definition-mappings-search-controls definition-mappings-reference-search">
            <AppInput
              id="reference-data-search-query"
              label="Search code lists"
              type="search"
              value={referenceDomainQuery}
              onChange={(event: any) => setReferenceDomainQuery(getFieldValue(event))}
              onInput={(event: any) => setReferenceDomainQuery(getFieldValue(event))}
              placeholder="Customer Status, Country Code, Currency Code"
            />
          </div>

          <div className="definition-mappings-results">
            <div className="definition-mappings-results-header">
              <h3>Governed reference domains</h3>
              <span className="definition-mappings-meta">
                {referenceDomainCount} code list{referenceDomainCount === 1 ? '' : 's'} • {referenceLookupValueCount} lookup value{referenceLookupValueCount === 1 ? '' : 's'}
              </span>
            </div>

            {referenceDomains.map((definition) => (
              <div key={definition.definitionId} className="definition-mappings-definition-card">
                <div>
                  <strong>{definition.definitionName}</strong>
                  <p>{definition.businessDefinition || 'No business definition supplied.'}</p>
                </div>
                <dl>
                  <div>
                    <dt>Definition ID</dt>
                    <dd>{definition.definitionId}</dd>
                  </div>
                  <div>
                    <dt>Owner</dt>
                    <dd>{definition.owner || 'n/a'}</dd>
                  </div>
                  <div>
                    <dt>Value domain</dt>
                    <dd>{[definition.valueDomain?.type, definition.valueDomain?.format].filter(Boolean).join(' / ') || 'n/a'}</dd>
                  </div>
                  <div>
                    <dt>Applies to</dt>
                    <dd>{definition.appliesTo?.length ? definition.appliesTo.join(', ') : 'n/a'}</dd>
                  </div>
                  <div>
                    <dt>Lookup values</dt>
                    <dd>{definition.valueDomain?.allowedValues?.length || 0}</dd>
                  </div>
                  <div>
                    <dt>Allowed values</dt>
                    <dd>
                      <div className="definition-mappings-value-chips">
                        {definition.valueDomain?.allowedValues?.map((value) => (
                          <span key={value} className="definition-mappings-value-chip">{value}</span>
                        )) || 'n/a'}
                      </div>
                    </dd>
                  </div>
                </dl>
              </div>
            ))}

            {!referenceDomainsLoading && referenceDomains.length === 0 && (
              <AppEmptyState
                title="No reference domains matched this search."
                description="Adjust the code-list search query or clear filters to load more governed domains."
              />
            )}
          </div>
        </section>
      )}
      </AppStack>
    </AppPageShell>
  )
}