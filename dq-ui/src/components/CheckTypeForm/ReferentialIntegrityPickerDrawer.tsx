import React, { useState } from 'react'
import { useDataProduct } from '../../contexts/DataProductContext'
import { DataObjectVersion, DataAttribute } from '../../types/dataProducts'
import { AppIcon } from '../app-primitives'
import './ReferentialIntegrityPickerDrawer.css'
import './ReferentialIntegrityPickerDrawer.css'

interface ReferentialIntegrityPickerDrawerProps {
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

export const ReferentialIntegrityPickerDrawer: React.FC<ReferentialIntegrityPickerDrawerProps> = ({
  isOpen,
  onClose,
  onSelect,
  excludeCurrentAttribute,
}) => {
  const normalizeIconName = (iconName: string): string => {
    return iconName.startsWith('app-icon-') ? iconName.slice('app-icon-'.length) : iconName
  }

  const { state, selectProduct, selectDataset, selectDataObject, selectVersion, filteredProducts, standaloneDatasets, loadDatasets, loadDataObjects, loadVersions, loadAttributes } = useDataProduct()
  
  const [expandedProducts, setExpandedProducts] = useState<Set<string>>(new Set())
  const [expandedDatasets, setExpandedDatasets] = useState<Set<string>>(new Set())
  const [expandedObjects, setExpandedObjects] = useState<Set<string>>(new Set())
  const [expandedVersions, setExpandedVersions] = useState<Set<string>>(new Set())
  const [selectedAttribute, setSelectedAttribute] = useState<DataAttribute | null>(null)

  const toggleProduct = (productId: string) => {
    setExpandedProducts(prev => {
      const next = new Set(prev)
      if (next.has(productId)) {
        next.delete(productId)
      } else {
        next.add(productId)
        loadDatasets(productId)
      }
      return next
    })
  }

  const toggleDataset = (datasetId: string) => {
    setExpandedDatasets(prev => {
      const next = new Set(prev)
      if (next.has(datasetId)) {
        next.delete(datasetId)
      } else {
        next.add(datasetId)
        const product = filteredProducts.find(p => p.datasets?.some(ds => ds.id === datasetId))
        if (product) {
          const dataset = product.datasets?.find(ds => ds.id === datasetId)
          if (dataset) loadDataObjects(datasetId)
        }
      }
      return next
    })
  }

  const toggleObject = (objectId: string) => {
    setExpandedObjects(prev => {
      const next = new Set(prev)
      if (next.has(objectId)) {
        next.delete(objectId)
      } else {
        next.add(objectId)
        loadVersions(objectId)
      }
      return next
    })
  }

  const toggleVersion = (versionId: string) => {
    setExpandedVersions(prev => {
      const next = new Set(prev)
      if (next.has(versionId)) {
        next.delete(versionId)
      } else {
        next.add(versionId)
        loadAttributes(versionId)
      }
      return next
    })
  }

  const handleSelectAttribute = async (version: DataObjectVersion, attribute: DataAttribute) => {
    if (state.selectedDataObject && state.selectedProduct) {
      onSelect({
        refWorkspaceId: state.selectedProduct.workspaceId || 'default',
        refDataObjectId: state.selectedDataObject.id,
        refDataObjectVersionId: version.id,
        refAttribute: attribute.name,
      })
      onClose()
    }
  }

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div className="referential-picker-drawer-backdrop" onClick={onClose} />
      )}

      {/* Drawer */}
      <div className={`referential-picker-drawer ${isOpen ? 'open' : 'closed'}`}>
        <div className="drawer-header">
          <h2 className="drawer-title">Select Reference Data Object & Attribute</h2>
          <button className="drawer-close" onClick={onClose} title="Close">
            <AppIcon name="times" />
          </button>
        </div>

        <div className="drawer-content">
          <div className="picker-tree">
            {filteredProducts.map(product => (
              <div key={product.id} className="tree-node">
                <div className="tree-item">
                  <button
                    className="tree-toggle"
                    onClick={() => toggleProduct(product.id)}
                    title={expandedProducts.has(product.id) ? 'Collapse' : 'Expand'}
                  >
                    <AppIcon name={expandedProducts.has(product.id) ? 'chevron-down' : 'chevron-right'} />
                  </button>
                  <span className="tree-label">
                    <AppIcon name={normalizeIconName(product.icon)} />
                    <span>{product.name}</span>
                  </span>
                </div>

                {expandedProducts.has(product.id) && product.datasets && (
                  <div className="tree-children">
                    {product.datasets.map(dataset => (
                      <div key={dataset.id} className="tree-node">
                        <div className="tree-item level-2">
                          <button
                            className="tree-toggle"
                            onClick={() => toggleDataset(dataset.id)}
                            title={expandedDatasets.has(dataset.id) ? 'Collapse' : 'Expand'}
                          >
                            <AppIcon name={expandedDatasets.has(dataset.id) ? 'chevron-down' : 'chevron-right'} />
                          </button>
                          <span className="tree-label">
                            <AppIcon name="database" />
                            <span>{dataset.name}</span>
                          </span>
                        </div>

                        {expandedDatasets.has(dataset.id) && dataset.dataObjects && (
                          <div className="tree-children">
                            {dataset.dataObjects.map(dataObject => (
                              <div key={dataObject.id} className="tree-node">
                                <div className="tree-item level-3">
                                  <button
                                    className="tree-toggle"
                                    onClick={() => toggleObject(dataObject.id)}
                                    title={expandedObjects.has(dataObject.id) ? 'Collapse' : 'Expand'}
                                  >
                                    <AppIcon name={expandedObjects.has(dataObject.id) ? 'chevron-down' : 'chevron-right'} />
                                  </button>
                                  <button
                                    className={`tree-label ${state.selectedDataObject?.id === dataObject.id ? 'active' : ''}`}
                                    onClick={() => selectDataObject(dataObject)}
                                  >
                                    <AppIcon name="box" />
                                    <span>{dataObject.name}</span>
                                  </button>
                                </div>

                                {expandedObjects.has(dataObject.id) && dataObject.versions && (
                                  <div className="tree-children">
                                    {dataObject.versions.map(version => (
                                      <div key={version.id} className="tree-node">
                                        <div className="tree-item level-4">
                                          <button
                                            className="tree-toggle"
                                            onClick={() => toggleVersion(version.id)}
                                            title={expandedVersions.has(version.id) ? 'Collapse' : 'Expand'}
                                          >
                                            <AppIcon name={expandedVersions.has(version.id) ? 'chevron-down' : 'chevron-right'} />
                                          </button>
                                          <button
                                            className={`tree-label ${state.selectedVersion?.id === version.id ? 'active' : ''}`}
                                            onClick={() => selectVersion(version)}
                                          >
                                            <AppIcon name="link" />
                                            <span>v{version.version}</span>
                                            <span className="version-date">{new Date(version.createdAt).toLocaleDateString()}</span>
                                          </button>
                                        </div>

                                        {expandedVersions.has(version.id) && version.attributes && (
                                          <div className="tree-children">
                                            {version.attributes.map(attr => (
                                              <div key={attr.id} className="tree-node">
                                                <div className="tree-item level-5 attribute">
                                                  <AppIcon name="arrow-right" />
                                                  <button
                                                    className="tree-label attribute-selector"
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
          </div>
        </div>

        {state.selectedVersion && (
          <div className="drawer-footer">
            <div className="summary-info">
              <div className="summary-item">
                <span className="summary-label">Version:</span>
                <span className="summary-value">{state.selectedDataObject?.name} v{state.selectedVersion.version}</span>
              </div>
            </div>
            <button className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        )}
      </div>
    </>
  )
}
