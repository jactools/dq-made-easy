import React, { useEffect, useMemo, useState } from 'react'
import { useDataProduct } from '../contexts/DataProductContext'
import { AppButton, AppModal, AppStack } from './app-primitives'
import { DataObject, DataObjectVersion, DataSet } from '../types/dataProducts'
import { HierarchyTreePanel, HierarchyTreeRow, HierarchyTreeStatus } from './HierarchyTree'
import { AppIcon } from './app-primitives'
import './TemplateAttributeCatalogPickerModal.css'

interface TemplateAttributeOption {
  id: string
  name: string
  dataObjectName?: string
  versionId?: string
  dataObjectVersion?: string
}

interface TemplateAttributeCatalogPickerModalProps {
  isOpen: boolean
  onClose: () => void
  attributeOptions: TemplateAttributeOption[]
  selectedAttributeIds: string[]
  onApply: (attributeIds: string[]) => void
}

export const TemplateAttributeCatalogPickerModal: React.FC<TemplateAttributeCatalogPickerModalProps> = ({
  isOpen,
  onClose,
  attributeOptions,
  selectedAttributeIds,
  onApply,
}) => {
  const {
    state,
    reset,
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
  const [draftSelectedIds, setDraftSelectedIds] = useState<Set<string>>(new Set())

  const selectableAttributeIds = useMemo(
    () => new Set(attributeOptions.map((attribute) => attribute.id)),
    [attributeOptions],
  )

  const selectedAttributeItems = useMemo(
    () => attributeOptions.filter((attribute) => draftSelectedIds.has(attribute.id)),
    [attributeOptions, draftSelectedIds],
  )

  useEffect(() => {
    if (!isOpen) {
      setDraftSelectedIds(new Set())
      return
    }

    reset()
    setExpandedProducts(new Set())
    setExpandedDatasets(new Set())
    setExpandedObjects(new Set())
    setExpandedVersions(new Set())
    setDraftSelectedIds(new Set(selectedAttributeIds))
  }, [isOpen, reset, selectedAttributeIds])

  const orderedSelectedIds = () =>
    attributeOptions
      .filter((attribute) => draftSelectedIds.has(attribute.id))
      .map((attribute) => attribute.id)

  const toggleDraftAttribute = (attributeId: string) => {
    setDraftSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(attributeId)) {
        next.delete(attributeId)
      } else {
        next.add(attributeId)
      }
      return next
    })
  }

  const handleApply = () => {
    onApply(orderedSelectedIds())
    onClose()
  }

  const handleSelectProduct = (productId: string) => {
    const product = filteredProducts.find((item) => item.id === productId)
    if (!product) return
    selectProduct(product)
    setExpandedProducts((prev) => new Set(prev).add(productId))
    void loadDatasets(productId)
    setExpandedDatasets(new Set())
    setExpandedObjects(new Set())
    setExpandedVersions(new Set())
  }

  const handleSelectDataset = (datasetId: string) => {
    for (const product of filteredProducts) {
      const dataset = product.datasets?.find((item) => item.id === datasetId)
      if (!dataset) continue

      selectDataset(dataset)
      setExpandedDatasets((prev) => new Set(prev).add(datasetId))
      void loadDataObjects(datasetId)
      setExpandedObjects(new Set())
      setExpandedVersions(new Set())
      return
    }

    const standaloneDataset = standaloneDatasets.find((item) => item.id === datasetId)
    if (!standaloneDataset) return
    selectDataset(standaloneDataset)
    setExpandedDatasets((prev) => new Set(prev).add(datasetId))
    void loadDataObjects(datasetId)
    setExpandedObjects(new Set())
    setExpandedVersions(new Set())
  }

  const handleSelectObject = async (dataObjectId: string) => {
    for (const product of filteredProducts) {
      for (const dataset of product.datasets || []) {
        const dataObject = dataset.dataObjects?.find((item) => item.id === dataObjectId)
        if (!dataObject) continue

        selectDataObject(dataObject)
        setExpandedObjects((prev) => new Set(prev).add(dataObjectId))
        await loadVersions(dataObjectId)
        setExpandedVersions(new Set())
        return
      }
    }

    for (const dataset of standaloneDatasets) {
      const dataObject = dataset.dataObjects?.find((item) => item.id === dataObjectId)
      if (!dataObject) continue

      selectDataObject(dataObject)
      setExpandedObjects((prev) => new Set(prev).add(dataObjectId))
      await loadVersions(dataObjectId)
      setExpandedVersions(new Set())
      return
    }
  }

  const handleSelectVersion = async (versionId: string) => {
    for (const product of filteredProducts) {
      for (const dataset of product.datasets || []) {
        for (const dataObject of dataset.dataObjects || []) {
          const version = dataObject.versions?.find((item) => item.id === versionId)
          if (!version) continue

          selectVersion(version)
          setExpandedVersions((prev) => new Set(prev).add(versionId))
          const loadedAttributes = await loadAttributes(versionId)
          if (loadedAttributes) {
            selectVersion({ ...version, attributes: loadedAttributes })
          }
          return
        }
      }
    }

    for (const dataset of standaloneDatasets) {
      for (const dataObject of dataset.dataObjects || []) {
        const version = dataObject.versions?.find((item) => item.id === versionId)
        if (!version) continue

        selectVersion(version)
        setExpandedVersions((prev) => new Set(prev).add(versionId))
        const loadedAttributes = await loadAttributes(versionId)
        if (loadedAttributes) {
          selectVersion({ ...version, attributes: loadedAttributes })
        }
        return
      }
    }
  }

  const toggleProduct = (productId: string) => {
    const isExpanded = expandedProducts.has(productId)
    setExpandedProducts((prev) => {
      const next = new Set(prev)
      if (next.has(productId)) {
        next.delete(productId)
      } else {
        next.add(productId)
      }
      return next
    })

    if (!isExpanded) {
      const product = filteredProducts.find((item) => item.id === productId)
      if (product) {
        selectProduct(product)
      }
      void loadDatasets(productId)
    }
  }

  const toggleDataset = (datasetId: string) => {
    const isExpanded = expandedDatasets.has(datasetId)
    setExpandedDatasets((prev) => {
      const next = new Set(prev)
      if (next.has(datasetId)) {
        next.delete(datasetId)
      } else {
        next.add(datasetId)
      }
      return next
    })

    if (!isExpanded) {
      void loadDataObjects(datasetId)
    }
  }

  const toggleObject = (objectId: string) => {
    const isExpanded = expandedObjects.has(objectId)
    setExpandedObjects((prev) => {
      const next = new Set(prev)
      if (next.has(objectId)) {
        next.delete(objectId)
      } else {
        next.add(objectId)
      }
      return next
    })

    if (!isExpanded) {
      void loadVersions(objectId)
    }
  }

  const toggleVersion = (versionId: string) => {
    const isExpanded = expandedVersions.has(versionId)
    setExpandedVersions((prev) => {
      const next = new Set(prev)
      if (next.has(versionId)) {
        next.delete(versionId)
      } else {
        next.add(versionId)
      }
      return next
    })

    if (!isExpanded) {
      void loadAttributes(versionId)
    }
  }

  const renderAttributeRows = (version: DataObjectVersion) => {
    const selectableAttributes = (version.attributes || []).filter((attribute) => selectableAttributeIds.has(attribute.id))

    if (isLoadingAttributes(version.id)) {
      return <HierarchyTreeStatus type="loading" label="Loading attributes..." />
    }

    if (selectableAttributes.length === 0) {
      return <HierarchyTreeStatus type="empty" label="No rule-selectable attributes in this version." />
    }

    return selectableAttributes.map((attribute) => {
      const active = draftSelectedIds.has(attribute.id)
      return (
        <div key={attribute.id} className="tree-node">
          <div className="tree-item level-5 attribute">
                <AppIcon name="arrow-right" />
            <button
              type="button"
              className={`tree-label attribute-selector ${active ? 'active' : ''}`.trim()}
              onClick={() => toggleDraftAttribute(attribute.id)}
            >
              <span className="attribute-name">{attribute.name}</span>
              <span className="attribute-type">{attribute.type}</span>
              {attribute.nullable && <span className="nullable-badge">nullable</span>}
            </button>
          </div>
        </div>
      )
    })
  }

  const renderVersionRows = (dataObject: DataObject) => {
    if (isLoadingVersions(dataObject.id)) {
      return <HierarchyTreeStatus type="loading" label="Loading versions..." />
    }

    if ((dataObject.versions || []).length === 0) {
      return <HierarchyTreeStatus type="empty" label="No versions" />
    }

    return (dataObject.versions || []).map((version) => (
      <div key={version.id} className="tree-node">
        <HierarchyTreeRow
          levelClass="level-4"
          isExpanded={expandedVersions.has(version.id)}
          onToggle={() => toggleVersion(version.id)}
          active={state.selectedVersion?.id === version.id}
          onSelect={() => void handleSelectVersion(version.id)}
          iconClass="link"
          label={`v${version.version}`}
          badge={<span className="version-date">{new Date(version.createdAt).toLocaleDateString()}</span>}
        />

        {expandedVersions.has(version.id) && (
          <div className="tree-children">
            {renderAttributeRows(version)}
          </div>
        )}
      </div>
    ))
  }

  const renderObjectRows = (dataset: DataSet) => {
    if (isLoadingObjects(dataset.id)) {
      return <HierarchyTreeStatus type="loading" label="Loading data objects..." />
    }

    if ((dataset.dataObjects || []).length === 0) {
      return <HierarchyTreeStatus type="empty" label="No data objects" />
    }

    return (dataset.dataObjects || []).map((dataObject) => (
      <div key={dataObject.id} className="tree-node">
        <HierarchyTreeRow
          levelClass="level-3"
          isExpanded={expandedObjects.has(dataObject.id)}
          onToggle={() => toggleObject(dataObject.id)}
          active={state.selectedDataObject?.id === dataObject.id}
          onSelect={() => void handleSelectObject(dataObject.id)}
          iconClass="box"
          label={dataObject.name}
        />

        {expandedObjects.has(dataObject.id) && (
          <div className="tree-children">
            {renderVersionRows(dataObject)}
          </div>
        )}
      </div>
    ))
  }

  const renderDatasetRows = (datasets: DataSet[], levelClass: string) =>
    datasets.map((dataset) => (
      <div key={dataset.id} className="tree-node">
        <HierarchyTreeRow
          levelClass={levelClass}
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
            {renderObjectRows(dataset)}
          </div>
        )}
      </div>
    ))

  return (
    <AppModal
      isOpen={isOpen}
      onClose={onClose}
      title="Select Attributes From Data Catalog"
      size="lg"
      bodyClassName="template-attribute-picker-shell-body"
      footer={
        <div className="template-attribute-picker-footer">
          <AppButton type="button" variant="secondary" onClick={onClose}>
            Cancel
          </AppButton>
          <AppButton
            type="button"
            onClick={handleApply}
            disabled={draftSelectedIds.size === 0}
          >
            Apply Selection
          </AppButton>
        </div>
      }
    >
      <AppStack gap="lg" className="template-attribute-picker-modal referential-picker-modal">
        <HierarchyTreePanel
          title="Browse data catalog"
          countLabel={`${filteredProducts.length} products${standaloneDatasets.length > 0 ? ` + ${standaloneDatasets.length} datasets` : ''}`}
          headerBadge={<span className="template-attribute-picker-selected-badge">{draftSelectedIds.size} selected</span>}
        >
          {filteredProducts.length === 0 && standaloneDatasets.length === 0 ? (
            <HierarchyTreeStatus type="empty" label="No catalog entries available." />
          ) : (
            <>
              {filteredProducts.map((product) => (
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
                      {isLoadingDatasets(product.id) ? (
                        <HierarchyTreeStatus type="loading" label="Loading datasets..." />
                      ) : (product.datasets || []).length === 0 ? (
                        <HierarchyTreeStatus type="empty" label="No datasets" />
                      ) : (
                        renderDatasetRows(product.datasets || [], 'level-2')
                      )}
                    </div>
                  )}
                </div>
              ))}

              {standaloneDatasets.length > 0 && (
                <div className="datasets-section">
                  <div className="section-header">
                    <h4>Standalone Datasets</h4>
                  </div>
                  {renderDatasetRows(standaloneDatasets, 'level-1-dataset')}
                </div>
              )}
            </>
          )}
        </HierarchyTreePanel>

        <div className="template-attribute-picker-selection-summary">
          <div className="template-attribute-picker-selection-header">
            <h3>Selected attributes</h3>
            <AppButton
              type="button"
              variant="tertiary"
              onClick={() => setDraftSelectedIds(new Set())}
              disabled={draftSelectedIds.size === 0}
            >
              Clear All
            </AppButton>
          </div>

          {selectedAttributeItems.length === 0 ? (
            <p className="template-attribute-picker-selection-empty">
              Select one or more attributes from the catalog tree.
            </p>
          ) : (
            <div className="template-attribute-picker-selection-list">
              {selectedAttributeItems.map((attribute) => (
                <button
                  key={attribute.id}
                  type="button"
                  className="template-attribute-picker-selection-chip"
                  onClick={() => toggleDraftAttribute(attribute.id)}
                >
                  <span>{attribute.dataObjectName ? `${attribute.dataObjectName} - ${attribute.name}` : attribute.name}</span>
                  <span aria-hidden="true">×</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </AppStack>
    </AppModal>
  )
}