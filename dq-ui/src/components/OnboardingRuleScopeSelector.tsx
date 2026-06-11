import React, { useState, useCallback, useMemo, useContext, useEffect } from 'react'
import { ModalShell } from './ModalShell'
import { AppButton, AppSelect, AppStack, AppBanner } from './app-primitives'
import { DataProductContext } from '../contexts/DataProductContext'
import { SettingsContext } from '../contexts/SettingsContext'
import { useNotifications } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import type { DataProduct, DataSet, DataObject, DataObjectVersion } from '../types/dataProducts'
import './OnboardingRuleScopeSelector.css'

export type OnboardingScopeType = 'workspace' | 'product' | 'dataset' | 'object'

export interface OnboardingProposalsResponse {
  scope_type: OnboardingScopeType
  scope_id: string
  total_attributes: number
  total_proposals: number
  proposals: any[]
  generated_at: string
}

interface OnboardingScopeSummaryResponse {
  scope_type: OnboardingScopeType
  scope_id: string
  workspace_id: string
  object_count: number
  attribute_count: number
  generated_at: string
}

export interface OnboardingScopeSelectorState {
  scopeType: OnboardingScopeType
  selectedProductId: string | null
  selectedDatasetId: string | null
  selectedObjectId: string | null
  selectedVersionId: string | null
}

interface OnboardingRuleScopeSelectorProps {
  isOpen: boolean
  onClose: () => void
  workspaceId: string
  onProposalsGenerated: (response: OnboardingProposalsResponse) => void
  initialState?: OnboardingScopeSelectorState | null
  onStateChange?: (state: OnboardingScopeSelectorState) => void
}

const ATTRIBUTE_COUNT_WARNING_THRESHOLD = 500

const countAttributesInObject = (obj: DataObject | DataObjectVersion): number => {
  // Count attributes based on the structure
  if ('attributes' in obj && Array.isArray(obj.attributes)) {
    return obj.attributes.length
  }

  if ('versions' in obj && Array.isArray(obj.versions)) {
    return obj.versions.reduce((sum, version) => sum + (Array.isArray(version.attributes) ? version.attributes.length : 0), 0)
  }

  return 0
}

const countAttributesInDataset = (dataset: DataSet): number => {
  if (!dataset.dataObjects || !Array.isArray(dataset.dataObjects)) {
    return 0
  }
  return dataset.dataObjects.reduce((sum, obj) => sum + countAttributesInObject(obj), 0)
}

const countAttributesInProduct = (product: DataProduct): number => {
  if (!product.datasets || !Array.isArray(product.datasets)) {
    return 0
  }
  return product.datasets.reduce((sum, dataset) => sum + countAttributesInDataset(dataset), 0)
}

export const OnboardingRuleScopeSelector: React.FC<OnboardingRuleScopeSelectorProps> = ({
  isOpen,
  onClose,
  workspaceId,
  onProposalsGenerated,
  initialState,
  onStateChange,
}) => {
  const dataProductContext = useContext(DataProductContext)
  const settings = useContext(SettingsContext)
  const { addNotification } = useNotifications()

  const [scopeType, setScopeType] = useState<OnboardingScopeType>('workspace')
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null)
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null)
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null)
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [isLoadingProposals, setIsLoadingProposals] = useState(false)
  const [proposalError, setProposalError] = useState<string | null>(null)
  const [scopeSummary, setScopeSummary] = useState<OnboardingScopeSummaryResponse | null>(null)

  useEffect(() => {
    if (!isOpen || !initialState) {
      return
    }

    setScopeType(initialState.scopeType || 'workspace')
    setSelectedProductId(initialState.selectedProductId || null)
    setSelectedDatasetId(initialState.selectedDatasetId || null)
    setSelectedObjectId(initialState.selectedObjectId || null)
    setSelectedVersionId(initialState.selectedVersionId || null)
  }, [
    initialState,
    isOpen,
  ])

  useEffect(() => {
    if (!isOpen || !onStateChange) {
      return
    }

    onStateChange({
      scopeType,
      selectedProductId,
      selectedDatasetId,
      selectedObjectId,
      selectedVersionId,
    })
  }, [
    isOpen,
    onStateChange,
    scopeType,
    selectedProductId,
    selectedDatasetId,
    selectedObjectId,
    selectedVersionId,
  ])

  // Use all products (unfiltered by data browser search) but enforce active workspace scoping.
  const allProducts = useMemo(() => {
    const products = dataProductContext?.allProducts || []
    const normalizedWorkspaceId = String(workspaceId || '').trim()
    if (!normalizedWorkspaceId) {
      return products
    }
    return products.filter((product) => String(product.workspaceId || '').trim() === normalizedWorkspaceId)
  }, [dataProductContext?.allProducts, workspaceId])
  const isLoadingProducts = dataProductContext?.isLoadingProducts ?? true

  // Get datasets for selected product
  const datasets = useMemo(() => {
    if (!selectedProductId) return []
    const product = allProducts.find(p => p.id === selectedProductId)
    return product?.datasets || []
  }, [selectedProductId, allProducts])

  // Get objects for selected dataset
  const objects = useMemo(() => {
    if (!selectedDatasetId) return []
    const product = allProducts.find(p => p.id === selectedProductId)
    const dataset = product?.datasets?.find(d => d.id === selectedDatasetId)
    return dataset?.dataObjects || []
  }, [selectedDatasetId, selectedProductId, allProducts])

  // Get versions for selected object
  const versions = useMemo(() => {
    if (!selectedObjectId) return []
    const product = allProducts.find(p => p.id === selectedProductId)
    const dataset = product?.datasets?.find(d => d.id === selectedDatasetId)
    const obj = dataset?.dataObjects?.find(o => o.id === selectedObjectId)
    return obj?.versions || []
  }, [selectedObjectId, selectedDatasetId, selectedProductId, allProducts])

  // Calculate attribute count based on scope
  const attributeCount = useMemo(() => {
    switch (scopeType) {
      case 'workspace':
        // All attributes in workspace
        return allProducts.reduce(
          (sum, p) => sum + countAttributesInProduct(p),
          0
        )
      case 'product':
        if (!selectedProductId) return 0
        const product = allProducts.find(p => p.id === selectedProductId)
        return product ? countAttributesInProduct(product) : 0
      case 'dataset':
        if (!selectedDatasetId) return 0
        const product2 = allProducts.find(p => p.id === selectedProductId)
        const dataset = product2?.datasets?.find(d => d.id === selectedDatasetId)
        return dataset ? countAttributesInDataset(dataset) : 0
      case 'object':
        if (!selectedVersionId) return 0
        const product3 = allProducts.find(p => p.id === selectedProductId)
        const dataset2 = product3?.datasets?.find(d => d.id === selectedDatasetId)
        const obj = dataset2?.dataObjects?.find(o => o.id === selectedObjectId)
        const version = obj?.versions?.find(v => v.id === selectedVersionId)
        return version ? countAttributesInObject(version) : 0
      default:
        return 0
    }
  }, [scopeType, selectedProductId, selectedDatasetId, selectedObjectId, selectedVersionId, allProducts])

  const objectCount = useMemo(() => {
    switch (scopeType) {
      case 'workspace':
        return allProducts.reduce(
          (sum, p) => sum + (p.datasets?.reduce((dSum, d) => dSum + (d.dataObjects?.length || 0), 0) || 0),
          0
        )
      case 'product':
        if (!selectedProductId) return 0
        const product = allProducts.find(p => p.id === selectedProductId)
        return product?.datasets?.reduce((sum, d) => sum + (d.dataObjects?.length || 0), 0) || 0
      case 'dataset':
        if (!selectedDatasetId) return 0
        const product2 = allProducts.find(p => p.id === selectedProductId)
        const dataset = product2?.datasets?.find(d => d.id === selectedDatasetId)
        return dataset?.dataObjects?.length || 0
      case 'object':
        return 1
      default:
        return 0
    }
  }, [scopeType, selectedProductId, selectedDatasetId, allProducts])

  const showAttributeWarning = attributeCount > ATTRIBUTE_COUNT_WARNING_THRESHOLD

  const displayObjectCount = scopeSummary?.object_count ?? objectCount
  const displayAttributeCount = scopeSummary?.attribute_count ?? attributeCount

  const handleScopeTypeChange = useCallback((newType: string) => {
    setScopeType(newType as OnboardingScopeType)
    setSelectedProductId(null)
    setSelectedDatasetId(null)
    setSelectedObjectId(null)
    setSelectedVersionId(null)
  }, [])

  const handleProductChange = useCallback((productId: string) => {
    setSelectedProductId(productId)
    setSelectedDatasetId(null)
    setSelectedObjectId(null)
    setSelectedVersionId(null)
    if (dataProductContext && productId) {
      dataProductContext.loadDatasets(productId)
    }
  }, [dataProductContext])

  const handleDatasetChange = useCallback((datasetId: string) => {
    setSelectedDatasetId(datasetId)
    setSelectedObjectId(null)
    setSelectedVersionId(null)
    if (dataProductContext && selectedProductId && datasetId) {
      const product = dataProductContext.filteredProducts.find(p => p.id === selectedProductId)
      const dataset = product?.datasets?.find(d => d.id === datasetId)
      if (dataset) {
        dataProductContext.loadDataObjects(datasetId)
      }
    }
  }, [dataProductContext, selectedProductId])

  const handleObjectChange = useCallback((objectId: string) => {
    setSelectedObjectId(objectId)
    setSelectedVersionId(null)
    if (dataProductContext && selectedProductId && selectedDatasetId && objectId) {
      dataProductContext.loadVersions(objectId)
    }
  }, [dataProductContext, selectedProductId, selectedDatasetId])

  const handleVersionChange = useCallback((versionId: string) => {
    setSelectedVersionId(versionId)
    if (dataProductContext && versionId) {
      dataProductContext.loadAttributes(versionId)
    }
  }, [dataProductContext])

  const canProceed = () => {
    switch (scopeType) {
      case 'workspace':
        return true
      case 'product':
        return !!selectedProductId
      case 'dataset':
        return !!selectedDatasetId
      case 'object':
        return !!selectedVersionId
      default:
        return false
    }
  }

  const getScopeId = () => {
    switch (scopeType) {
      case 'workspace':
        return workspaceId
      case 'product':
        return selectedProductId || ''
      case 'dataset':
        return selectedDatasetId || ''
      case 'object':
        return selectedVersionId || ''
      default:
        return ''
    }
  }

  useEffect(() => {
    if (!isOpen) {
      return
    }

    if (!canProceed()) {
      setScopeSummary(null)
      return
    }

    const token = getAuthToken()
    if (!token) {
      setScopeSummary(null)
      return
    }

    const scopeId = getScopeId()
    if (!scopeId) {
      setScopeSummary(null)
      return
    }

    let cancelled = false

    const loadScopeSummary = async () => {
      try {
        const apiBase = toApiGroupV1Base('rulebuilder', settings?.applicationSettings?.apiBaseUrl)
        const response = await fetch(`${apiBase}/onboarding/scope-summary`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          credentials: 'include',
          body: JSON.stringify({
            scope_type: scopeType,
            scope_id: scopeId,
            workspace_id: workspaceId,
          }),
        })

        if (!response.ok) {
          if (!cancelled) {
            setScopeSummary(null)
          }
          return
        }

        const payload: OnboardingScopeSummaryResponse = await response.json()
        if (!cancelled) {
          setScopeSummary(payload)
        }
      } catch {
        if (!cancelled) {
          setScopeSummary(null)
        }
      }
    }

    void loadScopeSummary()

    return () => {
      cancelled = true
    }
  }, [isOpen, scopeType, selectedProductId, selectedDatasetId, selectedObjectId, selectedVersionId, settings?.applicationSettings?.apiBaseUrl, workspaceId])

  const handleProceed = async () => {
    setProposalError(null)
    setIsLoadingProposals(true)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings?.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      if (!token) {
        const errorMessage = 'Authentication required. Please sign in again and retry.'
        setProposalError(errorMessage)
        addNotification({
          type: 'error',
          title: 'Authentication required',
          message: errorMessage,
          duration: 5000,
        })
        return
      }

      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      }

      const response = await fetch(`${apiBase}/onboarding/generate-proposals`, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({
          scope_type: scopeType,
          scope_id: getScopeId(),
          workspace_id: workspaceId,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const errorMessage = errorData.detail?.message || errorData.detail || 'Failed to generate proposals'
        setProposalError(errorMessage)
        addNotification({
          type: 'error',
          title: 'Error generating proposals',
          message: errorMessage,
          duration: 5000,
        })
        return
      }

      const proposalsData: OnboardingProposalsResponse = await response.json()
      onProposalsGenerated(proposalsData)
      onClose()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unexpected error occurred'
      setProposalError(errorMessage)
      addNotification({
        type: 'error',
        title: 'Error',
        message: errorMessage,
        duration: 5000,
      })
    } finally {
      setIsLoadingProposals(false)
    }
  }

  const scopeTypeOptions = [
    { value: 'workspace', label: 'Entire Workspace' },
    { value: 'product', label: 'Data Product' },
    { value: 'dataset', label: 'Dataset' },
    { value: 'object', label: 'Data Object' },
  ]

  const productOptions = allProducts.map(p => ({
    value: p.id,
    label: p.name,
  }))

  const productPlaceholderOption = isLoadingProducts
    ? { value: '', label: '— Loading data products… —' }
    : { value: '', label: '— Select a data product —' }

  const datasetOptions = datasets.map(d => ({
    value: d.id,
    label: d.name,
  }))

  const objectOptions = objects.map(o => ({
    value: o.id,
    label: o.name,
  }))

  const versionOptions = versions.map(v => ({
    value: v.id,
    label: `v${v.version || 'unknown'}`,
  }))

  const footer = (
    <AppStack gap="md" alignment="end">
      <AppButton variant="secondary" onClick={onClose} disabled={isLoadingProposals}>
        Cancel
      </AppButton>
      <AppButton
        variant="primary"
        onClick={handleProceed}
        disabled={!canProceed() || isLoadingProposals}
        isLoading={isLoadingProposals}
      >
        Generate Proposals
      </AppButton>
    </AppStack>
  )

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title="Generate Standard Rules"
      size="md"
      footer={footer}
    >
      <AppStack gap="lg">
        <div>
          <p className="onboarding-scope-selector__description">
            Select the scope for which you want to generate standard rule proposals. The system will analyze all
            attributes in the selected scope and suggest applicable rules based on data type and naming patterns.
          </p>
        </div>

        <div className="onboarding-scope-selector__section">
          <label htmlFor="scope-type" className="onboarding-scope-selector__label">
            Scope
          </label>
          <AppSelect
            id="scope-type"
            value={scopeType}
            onChange={handleScopeTypeChange}
            options={scopeTypeOptions}
            disabled={isLoadingProposals}
            label={null}
          />
        </div>

        {scopeType !== 'workspace' && (
          <>
            {scopeType === 'product' && (
              <div className="onboarding-scope-selector__section">
                <label htmlFor="product-select" className="onboarding-scope-selector__label">
                  Data Product
                </label>
                <AppSelect
                  id="product-select"
                  value={selectedProductId || ''}
                  onChange={handleProductChange}
                  options={[productPlaceholderOption, ...productOptions]}
                  disabled={isLoadingProposals || isLoadingProducts}
                  label={null}
                />
              </div>
            )}

            {scopeType === 'dataset' && (
              <>
                <div className="onboarding-scope-selector__section">
                  <label htmlFor="product-select-2" className="onboarding-scope-selector__label">
                    Data Product
                  </label>
                  <AppSelect
                    id="product-select-2"
                    value={selectedProductId || ''}
                    onChange={handleProductChange}
                    options={[productPlaceholderOption, ...productOptions]}
                    disabled={isLoadingProposals || isLoadingProducts}
                    label={null}
                  />
                </div>

                {selectedProductId && (
                  <div className="onboarding-scope-selector__section">
                    <label htmlFor="dataset-select" className="onboarding-scope-selector__label">
                      Dataset
                    </label>
                    <AppSelect
                      id="dataset-select"
                      value={selectedDatasetId || ''}
                      onChange={handleDatasetChange}
                      options={[{ value: '', label: '— Select a dataset —' }, ...datasetOptions]}
                      disabled={isLoadingProposals || datasetOptions.length === 0}
                      label={null}
                    />
                  </div>
                )}
              </>
            )}

            {scopeType === 'object' && (
              <>
                <div className="onboarding-scope-selector__section">
                  <label htmlFor="product-select-3" className="onboarding-scope-selector__label">
                    Data Product
                  </label>
                  <AppSelect
                    id="product-select-3"
                    value={selectedProductId || ''}
                    onChange={handleProductChange}
                    options={[productPlaceholderOption, ...productOptions]}
                    disabled={isLoadingProposals || isLoadingProducts}
                    label={null}
                  />
                </div>

                {selectedProductId && (
                  <div className="onboarding-scope-selector__section">
                    <label htmlFor="dataset-select-2" className="onboarding-scope-selector__label">
                      Dataset
                    </label>
                    <AppSelect
                      id="dataset-select-2"
                      value={selectedDatasetId || ''}
                      onChange={handleDatasetChange}
                      options={[{ value: '', label: '— Select a dataset —' }, ...datasetOptions]}
                      disabled={isLoadingProposals || datasetOptions.length === 0}
                      label={null}
                    />
                  </div>
                )}

                {selectedDatasetId && (
                  <div className="onboarding-scope-selector__section">
                    <label htmlFor="object-select" className="onboarding-scope-selector__label">
                      Data Object
                    </label>
                    <AppSelect
                      id="object-select"
                      value={selectedObjectId || ''}
                      onChange={handleObjectChange}
                      options={[{ value: '', label: '— Select a data object —' }, ...objectOptions]}
                      disabled={isLoadingProposals || objectOptions.length === 0}
                      label={null}
                    />
                  </div>
                )}

                {selectedObjectId && (
                  <div className="onboarding-scope-selector__section">
                    <label htmlFor="version-select" className="onboarding-scope-selector__label">
                      Version
                    </label>
                    <AppSelect
                      id="version-select"
                      value={selectedVersionId || ''}
                      onChange={handleVersionChange}
                      options={[{ value: '', label: '— Select a version —' }, ...versionOptions]}
                      disabled={isLoadingProposals || versionOptions.length === 0}
                      label={null}
                    />
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* Summary */}
        <div className="onboarding-scope-selector__summary">
          <div className="onboarding-scope-selector__summary-item">
            <span className="onboarding-scope-selector__summary-label">Objects:</span>
            <span className="onboarding-scope-selector__summary-value">{displayObjectCount}</span>
          </div>
          <span className="onboarding-scope-selector__summary-separator">·</span>
          <div className="onboarding-scope-selector__summary-item">
            <span className="onboarding-scope-selector__summary-label">Attributes:</span>
            <span className="onboarding-scope-selector__summary-value">{displayAttributeCount}</span>
          </div>
        </div>

        {/* Warning for large scopes */}
        {displayAttributeCount > ATTRIBUTE_COUNT_WARNING_THRESHOLD && (
          <AppBanner
            variant="warning"
            title="Large scope detected"
            description={`This scope contains ${displayAttributeCount} attributes. Generating ${displayAttributeCount}+ proposals may take a moment and require scrolling to review. Consider selecting a smaller scope for faster navigation.`}
            icon="alert-triangle"
          />
        )}

        {/* Error display */}
        {proposalError && (
          <AppBanner
            variant="critical"
            title="Error"
            description={proposalError}
            icon="error"
          />
        )}
      </AppStack>
    </ModalShell>
  )
}
