import React, { useState } from 'react'
import { ModalShell } from '../ModalShell'
import { useDataProduct } from '../../contexts/DataProductContext'
import { DataObjectVersion, DataAttribute } from '../../types/dataProducts'
import { HierarchyTreePanel, HierarchyTreeRow, HierarchyTreeStatus } from '../HierarchyTree'
import './ReferentialIntegrityPickerModal.css'

interface ReferentialIntegrityPickerModalProps {
  isOpen: boolean
  onClose: () => void
  onSelect: (selection: {
    refWorkspaceId: string
    refDataObjectId: string
    refDataObjectVersionId: string
    refAttribute: string
  }) => void
  excludeCurrentAttribute?: string
}

export const ReferentialIntegrityPickerModal: React.FC<ReferentialIntegrityPickerModalProps> = ({
  isOpen,
  onClose,
  onSelect,
  excludeCurrentAttribute,
}) => {
  const {
    state,
    selectProduct,
    selectDataset,
    selectDataObject,
    selectVersion,
    filteredProducts,
    standaloneDatasets,
    loadDatasets,
    loadDataObjects,
    loadVersions,
    loadAttributes,
    isLoadingDatasets,
    isLoadingObjects,
    isLoadingVersions,
    isLoadingAttributes,
  } = useDataProduct()

  const [expandedProducts, setExpandedProducts] = useState<Set<string>>(new Set())
  const [expandedDatasets, setExpandedDatasets] = useState<Set<string>>(new Set())
  const [expandedObjects, setExpandedObjects] = useState<Set<string>>(new Set())
  const [expandedVersions, setExpandedVersions] = useState<Set<string>>(new Set())
  const [selectedAttribute, setSelectedAttribute] = useState<DataAttribute | null>(null)

  const toggleProduct = (productId: string) => {
    const product = filteredProducts.find(p => p.id === productId)
    if (!product) return

    const isExpanded = expandedProducts.has(productId)
    setExpandedProducts(prev => {
      const next = new Set(prev)
      if (next.has(productId)) {
        next.delete(productId)
      } else {
        next.add(productId)
      }
      return next
    })

    if (!isExpanded) {
      selectProduct(product)
      loadDatasets(productId)
    }
  }

  const toggleDataset = (datasetId: string) => {
    const isExpanded = expandedDatasets.has(datasetId)
    setExpandedDatasets(prev => {
      const next = new Set(prev)
      if (next.has(datasetId)) {
        next.delete(datasetId)
      } else {
        next.add(datasetId)
      }
      return next
    })

    if (!isExpanded) {
      for (const product of filteredProducts) {
        const dataset = product.datasets?.find(ds => ds.id === datasetId)
        if (dataset) {
          selectDataset(dataset)
          loadDataObjects(datasetId)
          return
        }
      }
      const standaloneDataset = standaloneDatasets.find(ds => ds.id === datasetId)
      if (standaloneDataset) {
        selectDataset(standaloneDataset)
        loadDataObjects(datasetId)
      }
    }
  }

  const toggleObject = (objectId: string) => {
    const isExpanded = expandedObjects.has(objectId)
    setExpandedObjects(prev => {
      const next = new Set(prev)
      if (next.has(objectId)) {
        next.delete(objectId)
      } else {
        next.add(objectId)
      }
      return next
    })

    if (!isExpanded) {
      loadVersions(objectId)
    }
  }

  const toggleVersion = (versionId: string) => {
    const isExpanded = expandedVersions.has(versionId)
    setExpandedVersions(prev => {
      const next = new Set(prev)
      if (next.has(versionId)) {
        next.delete(versionId)
      } else {
        next.add(versionId)
      }
      return next
    })

    if (!isExpanded) {
      loadAttributes(versionId)
    }
  }

  const handleSelectProduct = (productId: string) => {
    const product = filteredProducts.find(p => p.id === productId)
    if (!product) return
    selectProduct(product)
    setExpandedProducts(prev => {
      const next = new Set(prev)
      next.add(productId)
      return next
    })
    loadDatasets(productId)
    setExpandedDatasets(new Set())
    setExpandedObjects(new Set())
    setExpandedVersions(new Set())
  }

  const handleSelectDataset = (datasetId: string) => {
    for (const product of filteredProducts) {
      const dataset = product.datasets?.find(ds => ds.id === datasetId)
      if (dataset) {
        selectDataset(dataset)
        setExpandedDatasets(prev => {
          const next = new Set(prev)
          next.add(datasetId)
          return next
        })
        loadDataObjects(datasetId)
        setExpandedObjects(new Set())
        setExpandedVersions(new Set())
        return
      }
    }
    const standaloneDataset = standaloneDatasets.find(ds => ds.id === datasetId)
    if (standaloneDataset) {
      selectDataset(standaloneDataset)
      setExpandedDatasets(prev => {
        const next = new Set(prev)
        next.add(datasetId)
        return next
      })
      loadDataObjects(datasetId)
      setExpandedObjects(new Set())
      setExpandedVersions(new Set())
    }
  }

  const handleSelectObject = async (dataObjectId: string) => {
    for (const product of filteredProducts) {
      for (const dataset of product.datasets || []) {
        const dataObject = dataset.dataObjects?.find(obj => obj.id === dataObjectId)
        if (dataObject) {
          selectDataObject(dataObject)
          setExpandedObjects(prev => {
            const next = new Set(prev)
            next.add(dataObjectId)
            return next
          })
          await loadVersions(dataObjectId)
          setExpandedVersions(new Set())
          return
        }
      }
    }

    for (const dataset of standaloneDatasets) {
      const dataObject = dataset.dataObjects?.find(obj => obj.id === dataObjectId)
      if (dataObject) {
        selectDataObject(dataObject)
        setExpandedObjects(prev => {
          const next = new Set(prev)
          next.add(dataObjectId)
          return next
        })
        await loadVersions(dataObjectId)
        setExpandedVersions(new Set())
        return
      }
    }
  }

  const handleSelectVersion = async (versionId: string) => {
    for (const product of filteredProducts) {
      for (const dataset of product.datasets || []) {
        for (const dataObject of dataset.dataObjects || []) {
          const version = dataObject.versions?.find(v => v.id === versionId)
          if (version) {
            selectVersion(version)
            setExpandedVersions(prev => {
              const next = new Set(prev)
              next.add(versionId)
              return next
            })
            const loadedAttributes = await loadAttributes(versionId)
            if (loadedAttributes) {
              selectVersion({ ...version, attributes: loadedAttributes })
            }
            return
          }
        }
      }
    }

    for (const dataset of standaloneDatasets) {
      for (const dataObject of dataset.dataObjects || []) {
        const version = dataObject.versions?.find(v => v.id === versionId)
        if (version) {
          selectVersion(version)
          setExpandedVersions(prev => {
            const next = new Set(prev)
            next.add(versionId)
            return next
          })
          const loadedAttributes = await loadAttributes(versionId)
          if (loadedAttributes) {
            selectVersion({ ...version, attributes: loadedAttributes })
          }
          return
        }
      }
    }
  }

  const handleSelectAttribute = async (version: DataObjectVersion, attribute: DataAttribute) => {
    setSelectedAttribute(attribute)
    if (state.selectedDataObject) {
      onSelect({
        refWorkspaceId: state.selectedProduct?.workspaceId || state.selectedDataset?.workspaceId || 'default',
        refDataObjectId: state.selectedDataObject.id,
        refDataObjectVersionId: version.id,
        refAttribute: attribute.name,
      })
      onClose()
    }
  }

  const handleConfirmSelection = () => {
    if (selectedAttribute && state.selectedVersion && state.selectedDataObject) {
      onSelect({
        refWorkspaceId: state.selectedProduct?.workspaceId || state.selectedDataset?.workspaceId || 'default',
        refDataObjectId: state.selectedDataObject.id,
        refDataObjectVersionId: state.selectedVersion.id,
        refAttribute: selectedAttribute.name,
      })
      onClose()
    }
  }

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title="Select Reference Data Object & Attribute"
      size="lg"
      footer={
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleConfirmSelection}
            disabled={!selectedAttribute || !state.selectedVersion}
          >
            Select
          </button>
        </div>
      }
    >
      <div className="referential-picker-modal">
        <HierarchyTreePanel
          title="Navigate by Product"
          countLabel={`${filteredProducts.length} products${standaloneDatasets.length > 0 ? ` + ${standaloneDatasets.length} datasets` : ''}`}
        >
            {filteredProducts.map(product => (
              <div key={product.id} className="tree-node">
                <HierarchyTreeRow
                  isExpanded={expandedProducts.has(product.id)}
                  onToggle={() => toggleProduct(product.id)}
                  active={state.selectedProduct?.id === product.id}
                  onSelect={() => handleSelectProduct(product.id)}
                  iconClass={product.icon}
                  label={product.name}
                  badge={
                    product.workspaceId ? (
                      <span className="workspace-badge-small" title={`Workspace: ${product.workspaceId}`}>
                        {product.workspaceId}
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
                        onSelect={() => handleSelectDataset(dataset.id)}
                        iconClass="database"
                        label={dataset.name}
                        badge={
                          dataset.workspaceId ? (
                            <span className="workspace-badge-small" title={`Workspace: ${dataset.workspaceId}`}>
                              {dataset.workspaceId}
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
                                onSelect={() => handleSelectObject(dataObject.id)}
                                iconClass="box"
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
                                        onSelect={() => handleSelectVersion(version.id)}
                                        iconClass="link"
                                        label={`v${version.version}`}
                                        badge={<span className="version-date">{new Date(version.createdAt).toLocaleDateString()}</span>}
                                      />

                                      {expandedVersions.has(version.id) && (
                                        <div className="tree-children">
                                          {isLoadingAttributes(version.id) && (
                                            <HierarchyTreeStatus type="loading" label="Loading attributes..." />
                                          )}
                                          {!isLoadingAttributes(version.id) && version.attributes && version.attributes.length === 0 && (
                                            <HierarchyTreeStatus type="empty" label="No attributes" />
                                          )}
                                          {version.attributes && version.attributes
                                            .filter(attr => attr.name !== excludeCurrentAttribute)
                                            .map(attr => (
                                            <div key={attr.id} className="tree-node">
                                              <div className="tree-item level-5 attribute">
                                                <span className="tree-attribute-arrow" aria-hidden="true">→</span>
                                                <button
                                                  className={`tree-label attribute-selector ${selectedAttribute?.id === attr.id ? 'active' : ''}`}
                                                  onClick={() => handleSelectAttribute(version, attr)}
                                                >
                                                  <span className="attribute-name">{attr.name}</span>
                                                  <span className="attribute-type">{attr.type}</span>
                                                  {attr.nullable && <span className="nullable-badge">nullable</span>}
                                                </button>
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

            {standaloneDatasets.length > 0 && (
              <div className="datasets-section">
                <div className="section-header">
                  <h4>Standalone Datasets</h4>
                </div>
                {standaloneDatasets.map(dataset => (
                  <div key={dataset.id} className="tree-node">
                    <HierarchyTreeRow
                      levelClass="level-1-dataset"
                      isExpanded={expandedDatasets.has(dataset.id)}
                      onToggle={() => toggleDataset(dataset.id)}
                      active={state.selectedDataset?.id === dataset.id}
                      onSelect={() => handleSelectDataset(dataset.id)}
                      iconClass="database"
                      label={dataset.name}
                      badge={
                        dataset.workspaceId ? (
                          <span className="workspace-badge-small" title={`Workspace: ${dataset.workspaceId}`}>
                            {dataset.workspaceId}
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
                            onSelect={() => handleSelectObject(dataObject.id)}
                            iconClass="box"
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
                                    onSelect={() => handleSelectVersion(version.id)}
                                    iconClass="link"
                                    label={`v${version.version}`}
                                    badge={<span className="version-date">{new Date(version.createdAt).toLocaleDateString()}</span>}
                                  />

                                  {expandedVersions.has(version.id) && (
                                    <div className="tree-children">
                                      {isLoadingAttributes(version.id) && (
                                        <HierarchyTreeStatus type="loading" label="Loading attributes..." />
                                      )}
                                      {!isLoadingAttributes(version.id) && version.attributes && version.attributes.length === 0 && (
                                        <HierarchyTreeStatus type="empty" label="No attributes" />
                                      )}
                                      {version.attributes && version.attributes
                                        .filter(attr => attr.name !== excludeCurrentAttribute)
                                        .map(attr => (
                                          <div key={attr.id} className="tree-node">
                                            <div className="tree-item level-5 attribute">
                                              <span className="tree-attribute-arrow" aria-hidden="true">→</span>
                                              <button
                                                className={`tree-label attribute-selector ${selectedAttribute?.id === attr.id ? 'active' : ''}`}
                                                onClick={() => handleSelectAttribute(version, attr)}
                                              >
                                                <span className="attribute-name">{attr.name}</span>
                                                <span className="attribute-type">{attr.type}</span>
                                                {attr.nullable && <span className="nullable-badge">nullable</span>}
                                              </button>
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

        {state.selectedVersion && selectedAttribute && (
          <div className="picker-summary">
            <div className="summary-item">
              <span className="summary-label">Reference Object Version:</span>
              <span className="summary-value">{state.selectedDataObject?.name} v{state.selectedVersion.version}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Selected Attribute:</span>
              <span className="summary-value">{selectedAttribute.name} ({selectedAttribute.type})</span>
            </div>
          </div>
        )}
      </div>
    </ModalShell>
  )
}
