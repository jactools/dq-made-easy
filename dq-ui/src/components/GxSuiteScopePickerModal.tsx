import React, { useEffect, useMemo, useState } from 'react'
import { AppButton, AppModal, AppStack, AppTagPicker } from './app-primitives'
import { useDataProduct } from '../contexts/DataProductContext'
import type { DataAttribute, DataObjectVersion } from '../types/dataProducts'
import { HierarchyTreePanel, HierarchyTreeRow, HierarchyTreeStatus } from './HierarchyTree'
import { AppIcon } from './app-primitives'
import './CheckTypeForm/ReferentialIntegrityPickerModal.css'

export type GxSuiteScopeSelection =
  | {
      kind: 'data_product'
      dataProductId: string
      dataProductName: string
      workspaceId: string | null
      tagIds?: string[]
    }
  | {
      kind: 'dataset'
      datasetId: string
      datasetName: string
      workspaceId: string | null
      dataProductId: string | null
      dataProductName: string | null
      tagIds?: string[]
    }
  | {
      kind: 'data_object'
      dataObjectId: string
      dataObjectName: string
      datasetId: string | null
      datasetName: string | null
      dataProductId: string | null
      dataProductName: string | null
      workspaceId: string | null
      tagIds?: string[]
    }
  | {
      kind: 'data_object_version'
      dataObjectVersionId: string
      dataObjectId: string | null
      dataObjectName: string | null
      datasetId: string | null
      datasetName: string | null
      dataProductId: string | null
      dataProductName: string | null
      workspaceId: string | null
      tagIds?: string[]
    }
  | {
      kind: 'attribute'
      attributeId: string
      attributeName: string
      dataObjectVersionId: string
      dataObjectId: string | null
      dataObjectName: string | null
      datasetId: string | null
      datasetName: string | null
      dataProductId: string | null
      dataProductName: string | null
      workspaceId: string | null
      tagIds?: string[]
    }

interface GxSuiteScopePickerModalProps {
  isOpen: boolean
  onClose: () => void
  onSelect: (selection: GxSuiteScopeSelection) => void
}

type SelectedKind = GxSuiteScopeSelection['kind'] | null

type AttributeSelection = {
  version: DataObjectVersion
  attribute: DataAttribute
}

const getWorkspaceId = (workspaceId: unknown): string | null => {
  const normalized = String(workspaceId || '').trim()
  return normalized ? normalized : null
}

export const GxSuiteScopePickerModal: React.FC<GxSuiteScopePickerModalProps> = ({
  isOpen,
  onClose,
  onSelect,
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

  const [selectedKind, setSelectedKind] = useState<SelectedKind>(null)
  const [selectedAttribute, setSelectedAttribute] = useState<AttributeSelection | null>(null)
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([])

  useEffect(() => {
    if (!isOpen) {
      setExpandedProducts(new Set())
      setExpandedDatasets(new Set())
      setExpandedObjects(new Set())
      setExpandedVersions(new Set())
      setSelectedKind(null)
      setSelectedAttribute(null)
      setSelectedTagIds([])
      return
    }

    reset()
    setExpandedProducts(new Set())
    setExpandedDatasets(new Set())
    setExpandedObjects(new Set())
    setExpandedVersions(new Set())
    setSelectedKind(null)
    setSelectedAttribute(null)
    setSelectedTagIds([])
  }, [isOpen, reset])

  const availableTags = useMemo(() => {
    const seen = new Set<string>()
    const tags: string[] = []

    const addTags = (values: string[] | undefined) => {
      for (const value of values || []) {
        const tag = String(value || '').trim()
        const key = tag.toLowerCase()
        if (!tag || seen.has(key)) {
          continue
        }
        seen.add(key)
        tags.push(tag)
      }
    }

    for (const product of filteredProducts) {
      addTags(product.tags)
      for (const dataset of product.datasets || []) {
        addTags(dataset.tags)
        for (const dataObject of dataset.dataObjects || []) {
          addTags(dataObject.tags)
          for (const version of dataObject.versions || []) {
            addTags(version.tags)
            for (const attribute of version.attributes || []) {
              addTags(attribute.tags)
            }
          }
        }
      }
    }

    for (const dataset of standaloneDatasets) {
      addTags(dataset.tags)
      for (const dataObject of dataset.dataObjects || []) {
        addTags(dataObject.tags)
        for (const version of dataObject.versions || []) {
          addTags(version.tags)
          for (const attribute of version.attributes || []) {
            addTags(attribute.tags)
          }
        }
      }
    }

    return tags.sort((left, right) => left.localeCompare(right))
  }, [filteredProducts, standaloneDatasets])

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

  const handleSelectProduct = (productId: string) => {
    const product = filteredProducts.find((item) => item.id === productId)
    if (!product) return

    selectProduct(product)
    setSelectedKind('data_product')
    setSelectedAttribute(null)

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
      setSelectedKind('dataset')
      setSelectedAttribute(null)

      setExpandedDatasets((prev) => new Set(prev).add(datasetId))
      void loadDataObjects(datasetId)

      setExpandedObjects(new Set())
      setExpandedVersions(new Set())
      return
    }

    const standaloneDataset = standaloneDatasets.find((item) => item.id === datasetId)
    if (!standaloneDataset) return

    selectDataset(standaloneDataset)
    setSelectedKind('dataset')
    setSelectedAttribute(null)

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
        setSelectedKind('data_object')
        setSelectedAttribute(null)

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
      setSelectedKind('data_object')
      setSelectedAttribute(null)

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
          setSelectedKind('data_object_version')
          setSelectedAttribute(null)

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
        setSelectedKind('data_object_version')
        setSelectedAttribute(null)

        setExpandedVersions((prev) => new Set(prev).add(versionId))
        const loadedAttributes = await loadAttributes(versionId)
        if (loadedAttributes) {
          selectVersion({ ...version, attributes: loadedAttributes })
        }
        return
      }
    }
  }

  const handleSelectAttribute = (version: DataObjectVersion, attribute: DataAttribute) => {
    setSelectedAttribute({ version, attribute })
    setSelectedKind('attribute')
  }

  const confirmEnabled = useMemo(() => {
    if (!selectedKind) return false

    if (selectedKind === 'attribute') {
      return Boolean(selectedAttribute && state.selectedDataObject)
    }

    if (selectedKind === 'data_object_version') {
      return Boolean(state.selectedVersion)
    }

    if (selectedKind === 'data_object') {
      return Boolean(state.selectedDataObject)
    }

    if (selectedKind === 'dataset') {
      return Boolean(state.selectedDataset)
    }

    if (selectedKind === 'data_product') {
      return Boolean(state.selectedProduct)
    }

    return false
  }, [selectedAttribute, selectedKind, state.selectedDataObject, state.selectedDataset, state.selectedProduct, state.selectedVersion])

  const selectionSummary = useMemo(() => {
    if (!selectedKind) return 'Nothing selected.'

    if (selectedKind === 'attribute') {
      const attributeName = selectedAttribute?.attribute?.name
      const versionLabel = state.selectedVersion ? `v${state.selectedVersion.version}` : ''
      const objectName = state.selectedDataObject?.name || state.selectedDataObject?.id
      return attributeName && objectName
        ? `Attribute: ${attributeName} (${objectName} ${versionLabel})`
        : 'Attribute selection incomplete.'
    }

    if (selectedKind === 'data_object_version' && state.selectedVersion && state.selectedDataObject) {
      return `Data object version: ${state.selectedDataObject.name} v${state.selectedVersion.version}`
    }

    if (selectedKind === 'data_object' && state.selectedDataObject) {
      return `Data object: ${state.selectedDataObject.name}`
    }

    if (selectedKind === 'dataset' && state.selectedDataset) {
      return `Dataset: ${state.selectedDataset.name}`
    }

    if (selectedKind === 'data_product' && state.selectedProduct) {
      return `Data product: ${state.selectedProduct.name}`
    }

    return 'Selection incomplete.'
  }, [selectedAttribute, selectedKind, state.selectedDataObject, state.selectedDataset, state.selectedProduct, state.selectedVersion])

  const handleConfirm = () => {
    if (!selectedKind) {
      return
    }

    const workspaceId =
      getWorkspaceId(state.selectedProduct?.workspaceId) ||
      getWorkspaceId(state.selectedDataset?.workspaceId) ||
      null

    if (selectedKind === 'data_product' && state.selectedProduct) {
      onSelect({
        kind: 'data_product',
        dataProductId: state.selectedProduct.id,
        dataProductName: state.selectedProduct.name,
        workspaceId,
        tagIds: selectedTagIds,
      })
      onClose()
      return
    }

    if (selectedKind === 'dataset' && state.selectedDataset) {
      onSelect({
        kind: 'dataset',
        datasetId: state.selectedDataset.id,
        datasetName: state.selectedDataset.name,
        workspaceId,
        dataProductId: state.selectedProduct?.id ?? state.selectedDataset.productId ?? null,
        dataProductName: state.selectedProduct?.name ?? null,
        tagIds: selectedTagIds,
      })
      onClose()
      return
    }

    if (selectedKind === 'data_object' && state.selectedDataObject) {
      onSelect({
        kind: 'data_object',
        dataObjectId: state.selectedDataObject.id,
        dataObjectName: state.selectedDataObject.name,
        datasetId: state.selectedDataset?.id ?? null,
        datasetName: state.selectedDataset?.name ?? null,
        dataProductId: state.selectedProduct?.id ?? state.selectedDataset?.productId ?? null,
        dataProductName: state.selectedProduct?.name ?? null,
        workspaceId,
        tagIds: selectedTagIds,
      })
      onClose()
      return
    }

    if (selectedKind === 'data_object_version' && state.selectedVersion) {
      onSelect({
        kind: 'data_object_version',
        dataObjectVersionId: state.selectedVersion.id,
        dataObjectId: state.selectedDataObject?.id ?? null,
        dataObjectName: state.selectedDataObject?.name ?? null,
        datasetId: state.selectedDataset?.id ?? null,
        datasetName: state.selectedDataset?.name ?? null,
        dataProductId: state.selectedProduct?.id ?? state.selectedDataset?.productId ?? null,
        dataProductName: state.selectedProduct?.name ?? null,
        workspaceId,
        tagIds: selectedTagIds,
      })
      onClose()
      return
    }

    if (selectedKind === 'attribute' && selectedAttribute) {
      onSelect({
        kind: 'attribute',
        attributeId: selectedAttribute.attribute.id,
        attributeName: selectedAttribute.attribute.name,
        dataObjectVersionId: selectedAttribute.version.id,
        dataObjectId: state.selectedDataObject?.id ?? null,
        dataObjectName: state.selectedDataObject?.name ?? null,
        datasetId: state.selectedDataset?.id ?? null,
        datasetName: state.selectedDataset?.name ?? null,
        dataProductId: state.selectedProduct?.id ?? state.selectedDataset?.productId ?? null,
        dataProductName: state.selectedProduct?.name ?? null,
        workspaceId,
        tagIds: selectedTagIds,
      })
      onClose()
    }
  }

  const renderAttributeRows = (version: DataObjectVersion) => {
    if (isLoadingAttributes(version.id)) {
      return <HierarchyTreeStatus type="loading" label="Loading attributes..." />
    }

    if ((version.attributes || []).length === 0) {
      return <HierarchyTreeStatus type="empty" label="No attributes" />
    }

    return (version.attributes || []).map((attribute) => {
      const active = selectedAttribute?.attribute.id === attribute.id
      return (
        <div key={attribute.id} className="tree-node">
          <div className="tree-item level-5 attribute">
                <AppIcon name="arrow-right" />
            <button
              type="button"
              className={`tree-label attribute-selector ${active ? 'active' : ''}`.trim()}
              onClick={() => handleSelectAttribute(version, attribute)}
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

  const renderVersionRows = (dataObject: any) => {
    if (isLoadingVersions(dataObject.id)) {
      return <HierarchyTreeStatus type="loading" label="Loading versions..." />
    }

    if ((dataObject.versions || []).length === 0) {
      return <HierarchyTreeStatus type="empty" label="No versions" />
    }

    return (dataObject.versions || []).map((version: DataObjectVersion) => (
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

  const renderObjectRows = (dataset: any) => {
    if (isLoadingObjects(dataset.id)) {
      return <HierarchyTreeStatus type="loading" label="Loading data objects..." />
    }

    if ((dataset.dataObjects || []).length === 0) {
      return <HierarchyTreeStatus type="empty" label="No data objects" />
    }

    return (dataset.dataObjects || []).map((dataObject: any) => (
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

  const renderDatasetRows = (datasets: any[], levelClass: string) =>
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

  const countLabel = useMemo(() => {
    return `${filteredProducts.length} products${standaloneDatasets.length > 0 ? ` + ${standaloneDatasets.length} datasets` : ''}`
  }, [filteredProducts.length, standaloneDatasets.length])

  return (
    <AppModal
      isOpen={isOpen}
      onClose={onClose}
      title="Browse Data Catalog"
      size="lg"
      bodyClassName="referential-picker-modal-body"
      footer={
        <div className="modal-footer">
          <AppButton variant="secondary" type="button" onClick={onClose}>
            Cancel
          </AppButton>
          <AppButton type="button" onClick={handleConfirm} disabled={!confirmEnabled}>
            Select
          </AppButton>
        </div>
      }
    >
      <AppStack gap="lg" className="referential-picker-modal">
        <AppTagPicker
          label="Execution tags"
          selectedTags={selectedTagIds}
          availableTags={availableTags}
          onChange={setSelectedTagIds}
          hint="Choose one or more tags to narrow execution scope. New tags can be created inline."
        />

        <HierarchyTreePanel title="Browse data catalog" countLabel={countLabel}>
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

        <div className="picker-summary">
          <div className="summary-item">
            <span className="summary-label">Selected level</span>
            <span className="summary-value">{selectedKind ? selectedKind.replaceAll('_', ' ') : 'none'}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Selected item</span>
            <span className="summary-value">{selectionSummary}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Selected tags</span>
            <span className="summary-value">{selectedTagIds.length > 0 ? selectedTagIds.join(', ') : 'none'}</span>
          </div>
        </div>
      </AppStack>
    </AppModal>
  )
}
