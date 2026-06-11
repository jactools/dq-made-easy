import React, { useState, useEffect, useMemo, useRef } from 'react'
import { useDataProduct } from '../contexts/DataProductContext'
import { useAuth } from '../hooks/useKeycloak'
import { useSettings } from '../hooks/useContexts'
import { useAsyncRequests, useTrackedAsyncRequest } from '../hooks/useAsyncRequests'
import { DataProduct, DataSet, DataObject, DataObjectVersion, DataDelivery, DataAttribute, DefinitionMappingTarget } from '../types/dataProducts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { Button } from './Button'
import { HierarchyTreePanel, HierarchyTreeRow, HierarchyTreeStatus } from './HierarchyTree'
import { AdhocRuleExecutionModal } from './AdhocRuleExecutionModal'
import { WorkspaceScopeSegmentedControl, type WorkspaceScope } from './WorkspaceScopeSegmentedControl'
import { getWorkspaceDisplayName } from './WorkspaceSelector'
import { AppIcon, AppPageHeader, AppPageShell } from './app-primitives'
import { DEFAULT_SEARCH_MINIMUM_LENGTH, matchesTokenizedSearch } from '../utils/listFilterState'
import { snakeToCamel } from '../utils/caseConverters'
import './DataBrowser.css'

interface DataBrowserProps {
  viewScope?: 'my' | 'team' | 'all' | 'global'
  onOpenDefinitionMappings?: (target: DefinitionMappingTarget) => void
}

const definitionStatusLabels: Record<string, string> = {
  explicit: 'Explicit',
  inherited: 'Inherited',
  explicit_unmapped: 'Cleared here',
  inherited_unmapped: 'Inherited clear',
  unmapped: 'Unmapped',
}

export const DataBrowser: React.FC<DataBrowserProps> = ({ viewScope = 'my', onOpenDefinitionMappings }) => {
  const settings = useSettings()
  const { 
    state, 
    selectProduct, 
    selectDataset, 
    selectDataObject, 
    selectVersion, 
    selectDelivery, 
    setSearchQuery, 
    filteredProducts, 
    standaloneDatasets: filteredStandaloneDatasets,
    loadDatasets,
    loadDataObjects,
    loadVersions,
    loadAttributes,
    isLoadingDatasets,
    isLoadingObjects,
    isLoadingVersions,
    isLoadingAttributes,
  } = useDataProduct()
  const auth = useAuth()
  const apiBase = useMemo(() => toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl), [settings.applicationSettings?.apiBaseUrl])
  const token = useMemo(() => getAuthToken(), [auth.isAuthenticated, auth.currentWorkspaceId])
  const { startTestDataGeneration } = useAsyncRequests()
  const [expandedProducts, setExpandedProducts] = useState<Set<string>>(new Set())
  const [expandedDatasets, setExpandedDatasets] = useState<Set<string>>(new Set())
  const [expandedObjects, setExpandedObjects] = useState<Set<string>>(new Set())
  const [expandedVersions, setExpandedVersions] = useState<Set<string>>(new Set())
  const [searchInput, setSearchInput] = useState('')
  const [attributeSearchInput, setAttributeSearchInput] = useState('')
  const [entityScope, setEntityScope] = useState<WorkspaceScope>(viewScope)
  const [selectedUserWorkspace, setSelectedUserWorkspace] = useState<string | null>(
    () => auth.user?.workspaceRoles[0]?.workspaceId || null
  )
  const [testData, setTestData] = useState<any>(null)
  const [testDataError, setTestDataError] = useState<string | null>(null)
  const [activeTestDataTaskId, setActiveTestDataTaskId] = useState<string | null>(null)
  const [showTestDataPanel, setShowTestDataPanel] = useState(false)
  const [testDataSampleCount, setTestDataSampleCount] = useState(10)
  const [highlightTestDataPanel, setHighlightTestDataPanel] = useState(false)
  const [isAdhocRunModalOpen, setIsAdhocRunModalOpen] = useState(false)
  const testDataPanelRef = useRef<HTMLDivElement>(null)
  const detailsContentRef = useRef<HTMLDivElement>(null)
  const datasetContractImportInputRef = useRef<HTMLInputElement | null>(null)
  const activeTestDataTask = useTrackedAsyncRequest(activeTestDataTaskId)
  const isGeneratingTestData = activeTestDataTask?.status === 'pending' || activeTestDataTask?.status === 'running'

  useEffect(() => {
    setEntityScope(viewScope)
  }, [viewScope])

  // Sync selectedUserWorkspace with auth.currentWorkspaceId when it changes
  useEffect(() => {
    if (auth.currentWorkspaceId) {
      setSelectedUserWorkspace(auth.currentWorkspaceId)
    }
  }, [auth.currentWorkspaceId])

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value
    setSearchInput(query)
    setSearchQuery(query)
  }

  const handleClearSearch = () => {
    setSearchInput('')
    setSearchQuery('')
  }

  const toggleProduct = (productId: string) => {
    setExpandedProducts(prev => {
      const next = new Set(prev)
      const isExpanding = !next.has(productId)
      
      if (isExpanding) {
        next.add(productId)
        // Lazy load datasets when expanding product
        loadDatasets(productId)
      } else {
        next.delete(productId)
      }
      
      return next
    })
  }

  const toggleDataset = (datasetId: string) => {
    setExpandedDatasets(prev => {
      const next = new Set(prev)
      const isExpanding = !next.has(datasetId)
      
      if (isExpanding) {
        next.add(datasetId)
        // Lazy load data objects when expanding dataset
        loadDataObjects(datasetId)
      } else {
        next.delete(datasetId)
      }
      
      return next
    })
  }

  const toggleObject = (objectId: string) => {
    setExpandedObjects(prev => {
      const next = new Set(prev)
      const isExpanding = !next.has(objectId)
      
      if (isExpanding) {
        next.add(objectId)
        // Lazy load versions when expanding object
        loadVersions(objectId)
      } else {
        next.delete(objectId)
      }
      
      return next
    })
  }

  const toggleVersion = (versionId: string) => {
    setExpandedVersions(prev => {
      const next = new Set(prev)
      next.has(versionId) ? next.delete(versionId) : next.add(versionId)
      return next
    })
  }

  const handleSelectProduct = (product: DataProduct) => {
    console.log('>>> [DataBrowser] handleSelectProduct:', product.id, product.name)
    selectProduct(product)
    // Auto-expand the product when selected
    setExpandedProducts(prev => {
      const next = new Set(prev)
      next.add(product.id)
      return next
    })
    // Lazy load datasets if not already loaded
    console.log('>>> [DataBrowser] About to call loadDatasets for:', product.id)
    loadDatasets(product.id)
    console.log('>>> [DataBrowser] Called loadDatasets')
    setExpandedDatasets(new Set())
    setExpandedObjects(new Set())
    setExpandedVersions(new Set())
  }

  const handleSelectDataset = (dataset: DataSet) => {
    selectDataset(dataset)
    // Auto-expand the dataset when selected
    setExpandedDatasets(prev => {
      const next = new Set(prev)
      next.add(dataset.id)
      return next
    })
    // Lazy load data objects if not already loaded
    loadDataObjects(dataset.id)
    setExpandedObjects(new Set())
    setExpandedVersions(new Set())
  }

  const handleSelectObject = async (dataObject: DataObject) => {
    // First set the selected object
    selectDataObject(dataObject)
    
    // Lazy load versions if not already loaded
    const loadedVersions = await loadVersions(dataObject.id)
    
    // Create updated object with loaded versions
    // This ensures the selected object has versions immediately without waiting for state updates
    if (loadedVersions && loadedVersions.length > 0) {
      const updatedDataObject = {
        ...dataObject,
        versions: loadedVersions
      }
      
      // Re-select with the updated object (which now has versions)
      selectDataObject(updatedDataObject)
      
      // Select the latest version (highest version number)
      const latestVersion = loadedVersions.reduce((latest, current) => 
        current.version > latest.version ? current : latest
      )
      
      // Lazy load attributes for the selected version
      const loadedAttributes = await loadAttributes(latestVersion.id)
      
      // Create version with attributes and select it
      const versionWithAttributes = {
        ...latestVersion,
        attributes: loadedAttributes || []
      }
      selectVersion(versionWithAttributes)
    }
  }

  const handleSelectVersion = async (version: DataObjectVersion) => {
    selectVersion(version)
    // Lazy load attributes for the selected version
    const loadedAttributes = await loadAttributes(version.id)
    
    // Update the selected version with loaded attributes
    if (loadedAttributes) {
      const versionWithAttributes = {
        ...version,
        attributes: loadedAttributes
      }
      selectVersion(versionWithAttributes)
    }
  }

  const handleGenerateTestData = async () => {
    if (!state.selectedVersion) return

    setTestData(null)
    setTestDataError(null)
    setShowTestDataPanel(false)

    try {
      const taskId = await startTestDataGeneration({
        versionId: state.selectedVersion.id,
        sampleCount: testDataSampleCount,
        versionName: state.selectedVersion.version,
        dataObjectId: state.selectedVersion.dataObjectId,
      })
      setActiveTestDataTaskId(taskId)
    } catch (error) {
      console.error('Failed to generate test data:', error)
      setTestDataError(
        error instanceof Error
          ? error.message
          : 'Failed to generate test data. Please try again.'
      )
    }
  }

  useEffect(() => {
    if (!activeTestDataTask) return

    if (activeTestDataTask.status === 'completed' && activeTestDataTask.result) {
      setTestData(activeTestDataTask.result)
      setTestDataError(null)
      setShowTestDataPanel(true)
      return
    }

    if (activeTestDataTask.status === 'failed' || activeTestDataTask.status === 'timed_out') {
      setTestDataError(activeTestDataTask.errorMessage || activeTestDataTask.message || 'Failed to generate test data. Please try again.')
    }
  }, [activeTestDataTask])

  const handleScrollToTestDataPanel = () => {
    const panel = testDataPanelRef.current
    if (panel) {
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setHighlightTestDataPanel(true)
    }

    setTimeout(() => {
      setHighlightTestDataPanel(false)
    }, 1400)
  }

  const downloadDataSetContract = async (format: 'yaml' | 'json' = 'yaml') => {
    if (!state.selectedDataset?.dataContractDownloadUrl) {
      return
    }

    try {
      const response = await fetch(`${apiBase}${state.selectedDataset.dataContractDownloadUrl}?format=${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (!response.ok) {
        throw new Error(`Failed to download dataset contract: ${response.status} ${response.statusText}`)
      }

      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      const downloadLink = document.createElement('a')
      downloadLink.href = blobUrl
      downloadLink.download = `${state.selectedDataset.id}.odcs.${format === 'json' ? 'json' : 'yaml'}`
      document.body.appendChild(downloadLink)
      downloadLink.click()
      downloadLink.remove()
      URL.revokeObjectURL(blobUrl)
    } catch (error) {
      console.error('Failed to download dataset contract:', error)
    }
  }

  const importDataSetContract = async (file: File) => {
    if (!state.selectedDataset) {
      return
    }

    try {
      const contractText = await file.text()
      const response = await fetch(`${apiBase}/data-catalog/v1/data-sets/${encodeURIComponent(state.selectedDataset.id)}/contract/import`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ contract_text: contractText }),
      })

      if (!response.ok) {
        throw new Error(`Failed to import dataset contract: ${response.status} ${response.statusText}`)
      }

      const payload = await response.json()
      const importedDataset = snakeToCamel<DataSet>(payload)
      selectDataset(importedDataset)
      const productId = importedDataset.productId || state.selectedProduct?.id || null
      if (productId) {
        await loadDatasets(productId)
      }
    } catch (error) {
      console.error('Failed to import dataset contract:', error)
    }
  }

  const handleDatasetContractImportChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) {
      return
    }
    await importDataSetContract(file)
  }


  const userTokens = new Set(
    [auth.user?.id, auth.user?.email, auth.user?.name]
      .map((value) => String(value || '').trim().toLowerCase())
      .filter(Boolean)
  )

  const workspaceFilter = entityScope === 'global' ? 'all' : 'current'

  const matchesOwnerScope = (owner?: string): boolean => {
    if (entityScope === 'all' || entityScope === 'global') {
      return true
    }

    const ownerToken = String(owner || '').trim().toLowerCase()
    if (!ownerToken) {
      return false
    }

    if (entityScope === 'team') {
      return !userTokens.has(ownerToken)
    }

    return userTokens.has(ownerToken)
  }

  // Filter products based on workspace and view scope filters
  const workspaceFilteredProducts = filteredProducts
    .map(product => {
      const filteredDatasets = product.datasets?.filter(ds => {
        if (workspaceFilter === 'current') {
          if (ds.workspaceId !== selectedUserWorkspace) {
            return false
          }
        }
        return matchesOwnerScope(ds.owner)
      }) || []

      return {
        ...product,
        datasets: filteredDatasets,
      }
    })
    .filter(product => {
      if (workspaceFilter === 'current' && product.workspaceId !== selectedUserWorkspace) {
        return false
      }

      return (product.datasets?.length || 0) > 0 || matchesOwnerScope(product.owner)
    })

  // Filter standalone datasets based on workspace and view scope filters
  const workspaceFilteredStandaloneDatasets = filteredStandaloneDatasets.filter(dataset => {
    if (workspaceFilter === 'current') {
      if (dataset.workspaceId !== selectedUserWorkspace) {
        return false
      }
    }
    return matchesOwnerScope(dataset.owner)
  })

  // Filter attributes based on search input
  const filteredAttributes = state.selectedVersion?.attributes?.filter(attr =>
    matchesTokenizedSearch([attr.name, attr.type, attr.format], attributeSearchInput)
  ) || []

  const definitionSummary = (state.selectedVersion?.attributes || []).reduce(
    (summary, attr) => {
      const status = attr.definitionMappingStatus || 'unmapped'
      if (attr.definitionId) {
        summary.mapped += 1
      } else {
        summary.unmapped += 1
      }
      if (status === 'inherited' || status === 'inherited_unmapped') {
        summary.inherited += 1
      }
      if (status === 'explicit' || status === 'explicit_unmapped') {
        summary.explicit += 1
      }
      return summary
    },
    { mapped: 0, unmapped: 0, inherited: 0, explicit: 0 }
  )

  const handleOpenDefinitionMappings = (attribute: DataAttribute) => {
    if (!state.selectedDataset || !state.selectedDataObject || !state.selectedVersion) {
      return
    }

    onOpenDefinitionMappings?.({
      productId: state.selectedProduct?.id || undefined,
      datasetId: state.selectedDataset.id,
      objectId: state.selectedDataObject.id,
      versionId: state.selectedVersion.id,
      attributeId: attribute.id,
    })
  }

  return (
    <AppPageShell className="data-browser-container">
      <AppPageHeader
        className="page-header"
        title="Browse Datasets & Schemas"
        description="Explore data products, datasets, versions, and attributes"
      >
        <div className="workspace-filter">
          <WorkspaceScopeSegmentedControl
            value={entityScope}
            onChange={setEntityScope}
            ariaLabel="Data catalog scope"
            label="Show:"
            className="workspace-filter-control"
            controlClassName="workspace-scope-control"
            labelClassName="filter-label"
          />
        </div>
      </AppPageHeader>

      <div className="search-bar-container">
        <div className="search-bar">
          <AppIcon name="magnifying-glass" />
          <input
            type="text"
            placeholder="Search datasets, objects, attributes..."
            value={searchInput}
            onChange={handleSearchChange}
            className="search-input"
          />
          {searchInput && (
            <button className="clear-search-btn" onClick={handleClearSearch} title="Clear search">
              <AppIcon name="times" />
            </button>
          )}
        </div>
        <div className="search-threshold-hint">Search applies at {DEFAULT_SEARCH_MINIMUM_LENGTH}+ characters.</div>
      </div>

      <div className="browser-layout">
        {/* Tree View */}
        <HierarchyTreePanel
          title="Navigate by Product"
          headerBadge={
            <>
              {workspaceFilter === 'current' && selectedUserWorkspace && (
                <span className="workspace-badge" title="Filtered to current workspace">
                  <AppIcon name="padlock-closed" />
                  {entityScope === 'my' ? 'My' : entityScope === 'team' ? "My Team's" : 'All'} in {getWorkspaceDisplayName(selectedUserWorkspace)}
                </span>
              )}
              {entityScope === 'global' && (
                <span className="workspace-badge all-workspaces" title="Showing all workspaces">
                  <AppIcon name="globe" />
                  All Workspaces
                </span>
              )}
            </>
          }
          countLabel={`${workspaceFilteredProducts.length} products ${workspaceFilteredStandaloneDatasets.length > 0 ? `+ ${workspaceFilteredStandaloneDatasets.length} datasets` : ''}`}
        >
            {workspaceFilteredProducts.map(product => (
              <div key={product.id} className="tree-node">
                <HierarchyTreeRow
                  isExpanded={expandedProducts.has(product.id)}
                  onToggle={() => toggleProduct(product.id)}
                  active={state.selectedProduct?.id === product.id}
                  onSelect={() => handleSelectProduct(product)}
                  iconClass={product.icon}
                  label={product.name}
                  badge={
                    product.workspaceId ? (
                      <span className="workspace-badge-small" title={`Workspace: ${product.workspaceId}`}>
                        {getWorkspaceDisplayName(product.workspaceId)}
                      </span>
                    ) : undefined
                  }
                />

                {expandedProducts.has(product.id) && (
                  <div className="tree-children">
                    {isLoadingDatasets(product.id) && (
                      <HierarchyTreeStatus type="loading" label="Loading datasets..." />
                    )}
                    {!isLoadingDatasets(product.id) && product.datasets && product.datasets.length === 0 && (
                      <HierarchyTreeStatus type="empty" label="No datasets" />
                    )}
                    {product.datasets && product.datasets.map(dataset => (
                      <div key={dataset.id} className="tree-node">
                        <HierarchyTreeRow
                          levelClass="level-2"
                          isExpanded={expandedDatasets.has(dataset.id)}
                          onToggle={() => toggleDataset(dataset.id)}
                          active={state.selectedDataset?.id === dataset.id}
                          onSelect={() => handleSelectDataset(dataset)}
                          iconClass="database"
                          label={dataset.name}
                          badge={
                            dataset.workspaceId ? (
                              <span className="workspace-badge-small" title={`Workspace: ${dataset.workspaceId}`}>
                                {getWorkspaceDisplayName(dataset.workspaceId)}
                              </span>
                            ) : undefined
                          }
                        />

                        {expandedDatasets.has(dataset.id) && (
                          <div className="tree-children">
                            {isLoadingObjects(dataset.id) && (
                              <HierarchyTreeStatus type="loading" label="Loading data objects..." />
                            )}
                            {!isLoadingObjects(dataset.id) && dataset.dataObjects && dataset.dataObjects.length === 0 && (
                              <HierarchyTreeStatus type="empty" label="No data objects" />
                            )}
                            {dataset.dataObjects && dataset.dataObjects.length > 0 && dataset.dataObjects.map(dataObject => (
                              <div key={dataObject.id} className="tree-node">
                                <HierarchyTreeRow
                                  levelClass="level-3"
                                  isExpanded={expandedObjects.has(dataObject.id)}
                                  onToggle={() => toggleObject(dataObject.id)}
                                  active={state.selectedDataObject?.id === dataObject.id}
                                  onSelect={() => handleSelectObject(dataObject)}
                                  iconClass={dataObject.icon}
                                  label={dataObject.name}
                                />

                                {expandedObjects.has(dataObject.id) && (
                                  <div className="tree-children">
                                    {isLoadingVersions(dataObject.id) && (
                                      <HierarchyTreeStatus type="loading" label="Loading versions..." />
                                    )}
                                    {!isLoadingVersions(dataObject.id) && dataObject.versions && dataObject.versions.length === 0 && (
                                      <HierarchyTreeStatus type="empty" label="No versions" />
                                    )}
                                    {dataObject.versions && dataObject.versions.map(version => (
                                      <div key={version.id} className="tree-node">
                                        <HierarchyTreeRow
                                          levelClass="level-4"
                                          isExpanded={expandedVersions.has(version.id)}
                                          onToggle={() => toggleVersion(version.id)}
                                          active={state.selectedVersion?.id === version.id}
                                          onSelect={() => handleSelectVersion(version)}
                                          iconClass="link"
                                          label={`V${version.version}`}
                                          badge={<span className="version-date">{new Date(version.createdAt).toLocaleDateString()}</span>}
                                        />

                                        {expandedVersions.has(version.id) && version.attributes && version.attributes.length > 0 && (
                                          <div className="tree-children">
                                            {version.attributes.map(attr => (
                                              <div key={attr.id} className="tree-node">
                                                <div className="tree-item level-5 attribute">
                                                  <AppIcon name="arrow-right" />
                                                  <span className="attribute-name">{attr.name}</span>
                                                  <span className="attribute-type">{attr.type}</span>
                                                  {attr.isCde && <span className="cde-badge" title="Critical Data Element">CDE</span>}
                                                  {attr.isCde && (attr.ruleCount === 0 || !attr.ruleCount ? 
                                                    <span className="rule-count-badge no-rules" title="No DQ rules assigned">0 rules</span>
                                                    : <span className="rule-count-badge has-rules" title={`${attr.ruleCount} DQ rule${attr.ruleCount === 1 ? '' : 's'} assigned`}>{attr.ruleCount} {attr.ruleCount === 1 ? 'rule' : 'rules'}</span>
                                                  )}
                                                  {attr.nullable && <span className="nullable-badge">nullable</span>}
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* Standalone Datasets Section */}
            {workspaceFilteredStandaloneDatasets.length > 0 && (
              <div className="datasets-section">
                <div className="section-header">
                  <h4>Standalone Datasets</h4>
                </div>
                {workspaceFilteredStandaloneDatasets.map(dataset => (
                  <div key={dataset.id} className="tree-node">
                    <HierarchyTreeRow
                      levelClass="level-1-dataset"
                      isExpanded={expandedDatasets.has(dataset.id)}
                      onToggle={() => toggleDataset(dataset.id)}
                      active={state.selectedDataset?.id === dataset.id}
                      onSelect={() => handleSelectDataset(dataset)}
                      iconClass="database"
                      label={dataset.name}
                      badge={
                        dataset.workspaceId ? (
                          <span className="workspace-badge-small" title={`Workspace: ${dataset.workspaceId}`}>
                            {getWorkspaceDisplayName(dataset.workspaceId)}
                          </span>
                        ) : undefined
                      }
                    />

                    {expandedDatasets.has(dataset.id) && (
                      <div className="tree-children">
                        {isLoadingObjects(dataset.id) && (
                          <HierarchyTreeStatus type="loading" label="Loading data objects..." />
                        )}
                        {!isLoadingObjects(dataset.id) && dataset.dataObjects && dataset.dataObjects.length === 0 && (
                          <HierarchyTreeStatus type="empty" label="No data objects" />
                        )}
                        {dataset.dataObjects && dataset.dataObjects.map(dataObject => (
                          <div key={dataObject.id} className="tree-node">
                            <HierarchyTreeRow
                              levelClass="level-3"
                              isExpanded={expandedObjects.has(dataObject.id)}
                              onToggle={() => toggleObject(dataObject.id)}
                              active={state.selectedDataObject?.id === dataObject.id}
                              onSelect={() => handleSelectObject(dataObject)}
                              iconClass={dataObject.icon}
                              label={dataObject.name}
                            />

                            {expandedObjects.has(dataObject.id) && (
                              <div className="tree-children">
                                {isLoadingVersions(dataObject.id) && (
                                  <HierarchyTreeStatus type="loading" label="Loading versions..." />
                                )}
                                {!isLoadingVersions(dataObject.id) && dataObject.versions && dataObject.versions.length === 0 && (
                                  <HierarchyTreeStatus type="empty" label="No versions" />
                                )}
                                {dataObject.versions && dataObject.versions.map(version => (
                                  <div key={version.id} className="tree-node">
                                    <HierarchyTreeRow
                                      levelClass="level-4"
                                      isExpanded={expandedVersions.has(version.id)}
                                      onToggle={() => toggleVersion(version.id)}
                                      active={state.selectedVersion?.id === version.id}
                                      onSelect={() => handleSelectVersion(version)}
                                      iconClass="link"
                                      label={`V${version.version}`}
                                      badge={<span className="version-date">{new Date(version.createdAt).toLocaleDateString()}</span>}
                                    />

                                    {expandedVersions.has(version.id) && version.attributes && version.attributes.length > 0 && (
                                      <div className="tree-children">
                                        {version.attributes.map(attr => (
                                          <div key={attr.id} className="tree-node">
                                            <div className="tree-item level-5 attribute">
                                              <AppIcon name="arrow-right" />
                                              <span className="attribute-name">{attr.name}</span>
                                              <span className="attribute-type">{attr.type}</span>
                                              {attr.nullable && <span className="nullable-badge">nullable</span>}
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
        </HierarchyTreePanel>

        {/* Details Panel */}
        <div className="details-panel">
          {state.selectedVersion ? (
            <div className={`details-content ${showTestDataPanel ? 'has-test-data' : ''}`} ref={detailsContentRef}>
              <div className="breadcrumb">
                {state.selectedProduct && (
                  <>
                    <span className="breadcrumb-item">{state.selectedProduct.name}</span>
                    <AppIcon name="chevron-right" />
                  </>
                )}
                {state.selectedDataset && (
                  <>
                    <span className="breadcrumb-item">{state.selectedDataset.name}</span>
                    <AppIcon name="chevron-right" />
                  </>
                )}
                {state.selectedDataObject && (
                  <>
                    <span className="breadcrumb-item">{state.selectedDataObject.name}</span>
                    <AppIcon name="chevron-right" />
                  </>
                )}
                {state.selectedVersion && (
                  <span className="breadcrumb-item active">V{state.selectedVersion.version}</span>
                )}
              </div>

              {state.selectedDataset && (
                <div className="dataset-contract-panel">
                  <div className="dataset-contract-copy">
                    <h3>Data Set Contract</h3>
                    <p>Download the ODCS contract for the selected dataset or import a contract file to update the catalog fields.</p>
                  </div>
                  <div className="dataset-contract-actions">
                    <Button
                      className="data-browser-action-btn"
                      variant="secondary-default"
                      onClick={() => void downloadDataSetContract('yaml')}
                      disabled={!state.selectedDataset.dataContractDownloadUrl}
                    >
                      <AppIcon slot="icon" name="download" />
                      Download YAML
                    </Button>
                    <Button
                      className="data-browser-action-btn"
                      variant="secondary-default"
                      onClick={() => void downloadDataSetContract('json')}
                      disabled={!state.selectedDataset.dataContractDownloadUrl}
                    >
                      <AppIcon slot="icon" name="download" />
                      Download JSON
                    </Button>
                    <Button
                      className="data-browser-action-btn"
                      variant="secondary-default"
                      onClick={() => datasetContractImportInputRef.current?.click()}
                    >
                      <AppIcon slot="icon" name="upload" />
                      Import Contract
                    </Button>
                    <input
                      ref={datasetContractImportInputRef}
                      type="file"
                      accept=".yaml,.yml,.json,application/x-yaml,application/json,text/yaml,text/json"
                      onChange={(event) => void handleDatasetContractImportChange(event)}
                      style={{ display: 'none' }}
                    />
                  </div>
                </div>
              )}

              {state.selectedDataObject && state.selectedDataObject.versions.length > 1 && (
                <div className="version-navigation">
                  <span className="nav-label">Versions:</span>
                  <div className="version-buttons">
                    {state.selectedDataObject.versions
                      .sort((a, b) => a.version - b.version)
                      .map(version => (
                        <button
                          key={version.id}
                          className={`version-btn ${state.selectedVersion?.id === version.id ? 'active' : ''}`}
                        onClick={() => handleSelectVersion(version)}
                          title={`Version ${version.version} - ${new Date(version.createdAt).toLocaleDateString()}`}
                        >
                          v{version.version}
                        </button>
                      ))}
                  </div>
                </div>
              )}

              <div className="version-header">
                <h2>{state.selectedDataObject?.name} v{state.selectedVersion.version}</h2>
                <div className="version-meta">
                  <span className="meta-item">
                    <AppIcon name="calendar" />
                    Schema created: {new Date(state.selectedVersion.createdAt).toLocaleDateString()}
                  </span>
                  <span className="meta-item">
                    <AppIcon name="table" />
                    {state.selectedVersion.attributes?.length || 0} attributes
                  </span>
                  {state.selectedVersion.deliveries && state.selectedVersion.deliveries.length > 0 && (() => {
                    const latestDelivery = [...state.selectedVersion.deliveries].sort((a, b) => 
                      new Date(b.deliveredAt).getTime() - new Date(a.deliveredAt).getTime()
                    )[0]
                    return (
                      <>
                        <span className="meta-item">
                          <AppIcon name="truck" />
                          Last delivered: {new Date(latestDelivery.deliveredAt).toLocaleDateString()}
                        </span>
                        <span className="meta-item">
                          <AppIcon name="database" />
                          {latestDelivery.recordCount.toLocaleString()} records
                        </span>
                        <span className="meta-item">
                          <AppIcon name="database" />
                          {(latestDelivery.sizeBytes / 1024 / 1024).toFixed(2)} MB
                        </span>
                        <span className="meta-item">
                          <span className={`status-badge dq-status-badge ${latestDelivery.status.toLowerCase()}`}>
                            {latestDelivery.status}
                          </span>
                        </span>
                      </>
                    )
                  })()}
                </div>
              </div>

              {state.selectedVersion.description && (
                <div className="description">
                  <p>{state.selectedVersion.description}</p>
                </div>
              )}

              <div className="attributes-section">
                <div className="attributes-header">
                  <h3>Attributes ({filteredAttributes.length} of {state.selectedVersion.attributes?.length || 0})</h3>
                  {(state.selectedVersion.attributes?.length || 0) > 5 && (
                    <div className="attribute-search">
                      <AppIcon name="magnifying-glass" />
                      <input
                        type="text"
                        placeholder="Search attributes..."
                        value={attributeSearchInput}
                        onChange={(e) => setAttributeSearchInput(e.target.value)}
                        className="attribute-search-input"
                      />
                      {attributeSearchInput && (
                        <button 
                          className="clear-search-btn" 
                          onClick={() => setAttributeSearchInput('')}
                          title="Clear search"
                        >
                          <AppIcon name="times" />
                        </button>
                      )}
                      <span className="attribute-search-hint">{DEFAULT_SEARCH_MINIMUM_LENGTH}+ chars</span>
                    </div>
                  )}
                </div>
                <div className="definition-summary-panel">
                  <div className="definition-summary-copy">
                    <h4>Governed Definitions</h4>
                    <p>This is a read-only view of the effective definition link for each attribute on this version.</p>
                  </div>
                  <div className="definition-summary-metrics">
                    <span className="definition-summary-chip mapped">{definitionSummary.mapped} mapped</span>
                    <span className="definition-summary-chip inherited">{definitionSummary.inherited} inherited</span>
                    <span className="definition-summary-chip explicit">{definitionSummary.explicit} explicit</span>
                    <span className="definition-summary-chip unmapped">{definitionSummary.unmapped} unmapped</span>
                  </div>
                </div>
                <div className="attributes-table-container">
                  {state.selectedVersion && isLoadingAttributes(state.selectedVersion.id) ? (
                    <div className="loading-state">
                      <AppIcon name="arrow-circle-repeat" />
                      <span>Loading attributes...</span>
                    </div>
                  ) : (
                    <div className="attributes-table">
                      <div className="table-header">
                        <div className="col-name">Name</div>
                        <div className="col-type">Type</div>
                        <div className="col-nullable">Nullable</div>
                        <div className="col-format">Format</div>
                        <div className="col-pk">Primary Key</div>
                        <div className="col-cde">CDE</div>
                        <div className="col-definition">Definition</div>
                      </div>
                    {filteredAttributes.length > 0 ? (
                      filteredAttributes.map(attr => (
                          <div key={attr.id} className="table-row">
                            <div className="col-name">
                              <code>{attr.name}</code>
                            </div>
                            <div className="col-type">
                              <span className="type-badge">{attr.type}</span>
                            </div>
                            <div className="col-nullable">
                              {attr.nullable ? (
                                <span className="status-badge dq-status-badge nullable">Yes</span>
                              ) : (
                                <span className="status-badge dq-status-badge required">No</span>
                              )}
                            </div>
                            <div className="col-format">
                              {attr.format ? <code className="format">{attr.format}</code> : <span className="muted">—</span>}
                            </div>
                            <div className="col-pk">
                              {attr.isPrimaryKey ? (
                                <span className="pk-label" title="Primary Key">PK</span>
                              ) : (
                                <span className="muted">—</span>
                              )}
                            </div>
                            <div className="col-cde">
                              {attr.isCde ? (
                                <div className="cde-with-rules">
                                  <span className="status-badge dq-status-badge cde" title="Critical Data Element - Requires DQ Rules">CDE</span>
                                  {attr.ruleCount === 0 || !attr.ruleCount ? (
                                    <span className="rule-count no-rules" title="No DQ rules assigned">0 rules</span>
                                  ) : (
                                    <span className="rule-count has-rules" title={`${attr.ruleCount} DQ rule${attr.ruleCount === 1 ? '' : 's'} assigned`}>{attr.ruleCount} rules</span>
                                  )}
                                </div>
                              ) : (
                                <span className="muted">—</span>
                              )}
                            </div>
                            <div className="col-definition">
                              <button
                                type="button"
                                className="definition-link-button"
                                onClick={() => handleOpenDefinitionMappings(attr)}
                                title={`Open Definition Mappings for ${attr.name}`}
                              >
                                <div className="definition-cell">
                              {attr.definitionId ? (
                                <>
                                  <code className="definition-id">{attr.definitionId}</code>
                                  <span className={`definition-status-chip ${attr.definitionMappingStatus || 'unmapped'}`}>
                                    {definitionStatusLabels[attr.definitionMappingStatus || 'unmapped']}
                                  </span>
                                  {attr.definitionMappingVersionId && attr.definitionMappingStatus?.startsWith('inherited') && (
                                    <span className="definition-source">Inherited from {attr.definitionMappingVersionId}</span>
                                  )}
                                </>
                              ) : (
                                <>
                                  <span className={`definition-status-chip ${attr.definitionMappingStatus || 'unmapped'}`}>
                                    {definitionStatusLabels[attr.definitionMappingStatus || 'unmapped']}
                                  </span>
                                  <span className="muted">No governed definition</span>
                                </>
                              )}
                                  <span className="definition-open-link">Open in Definition Mappings</span>
                                </div>
                              </button>
                            </div>
                          </div>
                      ))
                    ) : (
                      <div className="no-results">
                        <p>No attributes match your search</p>
                      </div>
                    )}
                  </div>
                  )}
                </div>
              </div>

              <div className="action-buttons">
                <Button className="data-browser-action-btn" variant="primary-default" onClick={handleGenerateTestData} disabled={isGeneratingTestData}>
                  <AppIcon slot="icon" name={isGeneratingTestData ? 'arrow-circle-repeat' : 'lightbulb'} className={isGeneratingTestData ? 'spin-icon' : ''} />
                  {isGeneratingTestData ? 'Generating...' : 'Generate Test Data'}
                </Button>
                <Button
                  className="data-browser-action-btn"
                  variant="secondary-default"
                  onClick={() => setIsAdhocRunModalOpen(true)}
                  disabled={!state.selectedVersion}
                >
                  <AppIcon slot="icon" name="play" />
                  Run Rules on This Version
                </Button>
                <Button className="data-browser-action-btn" variant="secondary-default">
                  <AppIcon slot="icon" name="download" />
                  Export Schema
                </Button>
              </div>

              <AdhocRuleExecutionModal
                isOpen={isAdhocRunModalOpen}
                onClose={() => setIsAdhocRunModalOpen(false)}
                mode="data_object_version"
                dataObjectVersionId={state.selectedVersion?.id}
                dataObjectVersionLabel={state.selectedDataObject
                  ? `${state.selectedDataObject.name} v${state.selectedVersion?.version ?? ''}`
                  : (state.selectedVersion?.id || '')}
              />

              {testDataError && (
                <div className="test-data-message error">
                  <AppIcon name="exclamation-circle" />
                  <span>{testDataError}</span>
                </div>
              )}

              {showTestDataPanel && testData && (
                <div className="test-data-message success">
                  <AppIcon name="check-circle" />
                  <span>
                    Test data generated ({testData.sampleCount} rows).
                  </span>
                  <button
                    type="button"
                    className="jump-to-test-data-btn"
                    onClick={handleScrollToTestDataPanel}
                  >
                    View generated data
                  </button>
                </div>
              )}

              {/* Test Data Panel */}
              {showTestDataPanel && testData && (
                <div className={`test-data-panel ${highlightTestDataPanel ? 'highlight' : ''}`} ref={testDataPanelRef}>
                  <div className="panel-header">
                    <h3>Generated Test Data</h3>
                    <button className="close-btn" onClick={() => setShowTestDataPanel(false)}>×</button>
                  </div>
                  <div className="panel-content">
                    <div className="test-data-info">
                      <div className="info-item">
                        <span className="label">Data Object Version:</span>
                        <span className="value">{testData.versionName}</span>
                      </div>
                      <div className="info-item">
                        <span className="label">Attributes:</span>
                        <span className="value">{testData.attributeCount}</span>
                      </div>
                      <div className="info-item">
                        <span className="label">Sample Count:</span>
                        <span className="value">{testData.sampleCount}</span>
                      </div>
                      <div className="info-item">
                        <span className="label">Generated At:</span>
                        <span className="value">{new Date(testData.generatedAt).toLocaleString()}</span>
                      </div>
                    </div>

                    <div className="test-samples-container">
                      <h4>Sample Data ({testData.samples.length} rows)</h4>
                      <div className="test-samples-table">
                        {testData.samples.length > 0 ? (
                          <>
                            <div className="table-header">
                              {testData.attributes?.map((attr: any) => (
                                <div key={attr.id} className="table-cell">
                                  <span className="attr-name">{attr.name}</span>
                                  <span className="attr-type">{attr.type}</span>
                                </div>
                              ))}
                            </div>
                            {testData.samples.map((sample: any, idx: number) => (
                              <div key={idx} className="table-row">
                                {Object.values(sample).map((value: any, vi: number) => (
                                  <div key={vi} className="table-cell">
                                    <code>{String(value)}</code>
                                  </div>
                                ))}
                              </div>
                            ))}
                          </>
                        ) : (
                          <div className="no-data">No samples generated</div>
                        )}
                      </div>
                    </div>

                    <div className="test-actions">
                      <div className="action-group">
                        <label htmlFor="sample-count-input" className="label">
                          Generate More Samples:
                        </label>
                        <div className="input-group">
                          <input
                            id="sample-count-input"
                            type="number"
                            min="1"
                            max="1000"
                            value={testDataSampleCount}
                            onChange={(e) => setTestDataSampleCount(Math.max(1, parseInt(e.target.value) || 10))}
                            className="count-input"
                          />
                          <Button onClick={handleGenerateTestData} disabled={isGeneratingTestData} className="data-browser-regenerate-btn" variant="secondary-default">
                            <AppIcon slot="icon" name="arrow-circle-repeat" className={isGeneratingTestData ? 'spin-icon' : ''} />
                            Regenerate
                          </Button>
                        </div>
                      </div>
                      <Button className="data-browser-test-action-btn" variant="primary-default" disabled>
                        <AppIcon slot="icon" name="check-alt" />
                        Test Selected Rules (Coming Soon)
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : state.selectedDataset ? (
            <div className="details-content" ref={detailsContentRef}>
              <div className="breadcrumb">
                {state.selectedProduct && (
                  <>
                    <span className="breadcrumb-item">{state.selectedProduct.name}</span>
                    <AppIcon name="chevron-right" />
                  </>
                )}
                <span className="breadcrumb-item active">{state.selectedDataset.name}</span>
              </div>

              <div className="dataset-contract-panel dataset-contract-panel-standalone">
                <div className="dataset-contract-copy">
                  <h3>Data Set Contract</h3>
                  <p>Download or import the dataset ODCS contract to update the catalog view.</p>
                </div>
                <div className="dataset-contract-actions">
                  <Button
                    className="data-browser-action-btn"
                    variant="secondary-default"
                    onClick={() => void downloadDataSetContract('yaml')}
                    disabled={!state.selectedDataset.dataContractDownloadUrl}
                  >
                    <AppIcon slot="icon" name="download" />
                    Download YAML
                  </Button>
                  <Button
                    className="data-browser-action-btn"
                    variant="secondary-default"
                    onClick={() => void downloadDataSetContract('json')}
                    disabled={!state.selectedDataset.dataContractDownloadUrl}
                  >
                    <AppIcon slot="icon" name="download" />
                    Download JSON
                  </Button>
                  <Button
                    className="data-browser-action-btn"
                    variant="secondary-default"
                    onClick={() => datasetContractImportInputRef.current?.click()}
                  >
                    <AppIcon slot="icon" name="upload" />
                    Import Contract
                  </Button>
                  <input
                    ref={datasetContractImportInputRef}
                    type="file"
                    accept=".yaml,.yml,.json,application/x-yaml,application/json,text/yaml,text/json"
                    onChange={(event) => void handleDatasetContractImportChange(event)}
                    style={{ display: 'none' }}
                  />
                </div>
              </div>

              <div className="empty-state dataset-contract-empty">
                <AppIcon name="database" style={{ fontSize: '48px', opacity: 0.3 }} />
                <h3>Select a Data Object Version</h3>
                <p>Open a version from the selected dataset to inspect attributes and run rules.</p>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <AppIcon name="database" style={{ fontSize: '48px', opacity: 0.3 }} />
              <h3>Select a Data Object Version</h3>
              <p>Choose a data object from the tree to view its schema and attributes</p>
            </div>
          )}
        </div>
      </div>
    </AppPageShell>
  )
}
