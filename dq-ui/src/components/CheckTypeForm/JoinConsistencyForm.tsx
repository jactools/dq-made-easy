import React, { useEffect, useMemo, useState } from 'react'
import { JoinConsistencyParams } from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { useDataProduct } from '../../contexts/DataProductContext'
import { DataAttribute, DataObject, DataObjectVersion, DataSet } from '../../types/dataProducts'
import { ActualityDateConfig, type ActualityDateFieldErrors } from './ActualityDateConfig'
import { JoinConsistencyFieldErrors } from './joinConsistencyValidation'
import './JoinConsistencyForm.css'

interface JoinConsistencyFormProps {
  params: Partial<JoinConsistencyParams>
  onChange: (params: JoinConsistencyParams) => void
  fieldErrors?: JoinConsistencyFieldErrors
}

const defaultParams = (params: Partial<JoinConsistencyParams>): JoinConsistencyParams => ({
  checkType: 'JOIN_CONSISTENCY',
  leftDataObjectVersionId: params.leftDataObjectVersionId ?? '',
  rightDataObjectVersionId: params.rightDataObjectVersionId ?? '',
  joinKeys: params.joinKeys && params.joinKeys.length > 0 ? params.joinKeys : [{ leftAttribute: '', rightAttribute: '' }],
  comparisons:
    params.comparisons && params.comparisons.length > 0
      ? params.comparisons
      : [{ leftAttribute: '', rightAttribute: '', mode: 'exact' }],
  actualityDate: {
    leftAttribute: params.actualityDate?.leftAttribute ?? '',
    rightAttribute: params.actualityDate?.rightAttribute ?? '',
    toleranceSource: 'DELIVERY_CONTRACT',
    contractId: params.actualityDate?.contractId ?? '',
    contractVersion: params.actualityDate?.contractVersion,
    resolvedToleranceValue: params.actualityDate?.resolvedToleranceValue,
    resolvedToleranceUnit: params.actualityDate?.resolvedToleranceUnit,
    overrideToleranceValue: params.actualityDate?.overrideToleranceValue,
    overrideToleranceUnit: params.actualityDate?.overrideToleranceUnit,
    overrideAllowed: params.actualityDate?.overrideAllowed,
    maxOverrideToleranceValue: params.actualityDate?.maxOverrideToleranceValue,
    maxOverrideToleranceUnit: params.actualityDate?.maxOverrideToleranceUnit,
  },
  minMatchRate: Number.isFinite(Number(params.minMatchRate)) ? Number(params.minMatchRate) : 100,
})

export const JoinConsistencyForm: React.FC<JoinConsistencyFormProps> = ({ params, onChange, fieldErrors }) => {
  const { filteredProducts, standaloneDatasets, loadDatasets, loadDataObjects, loadVersions, loadAttributes } = useDataProduct()
  const [leftScope, setLeftScope] = useState<'product' | 'standalone'>('product')
  const [leftProductId, setLeftProductId] = useState('')
  const [leftDatasetId, setLeftDatasetId] = useState('')
  const [leftObjectId, setLeftObjectId] = useState('')

  const [rightScope, setRightScope] = useState<'product' | 'standalone'>('product')
  const [rightProductId, setRightProductId] = useState('')
  const [rightDatasetId, setRightDatasetId] = useState('')
  const [rightObjectId, setRightObjectId] = useState('')

  const emit = (patch: Partial<JoinConsistencyParams>) => {
    onChange({
      ...defaultParams(params),
      ...patch,
      checkType: 'JOIN_CONSISTENCY',
    })
  }

  const updateJoinKey = (index: number, field: 'leftAttribute' | 'rightAttribute', value: string) => {
    const next = [...defaultParams(params).joinKeys]
    next[index] = {
      ...next[index],
      [field]: value,
    }
    emit({ joinKeys: next })
  }

  const addJoinKey = () => {
    emit({
      joinKeys: [...defaultParams(params).joinKeys, { leftAttribute: '', rightAttribute: '' }],
    })
  }

  const removeJoinKey = (index: number) => {
    const source = defaultParams(params).joinKeys
    if (source.length <= 1) return
    emit({ joinKeys: source.filter((_, i) => i !== index) })
  }

  const updateComparison = (
    index: number,
    field: 'leftAttribute' | 'rightAttribute' | 'mode',
    value: string,
  ) => {
    const next = [...defaultParams(params).comparisons]
    next[index] = {
      ...next[index],
      [field]: field === 'mode' ? (value as 'exact' | 'case_insensitive') : value,
    }
    emit({ comparisons: next })
  }

  const addComparison = () => {
    emit({
      comparisons: [
        ...defaultParams(params).comparisons,
        { leftAttribute: '', rightAttribute: '', mode: 'exact' },
      ],
    })
  }

  const removeComparison = (index: number) => {
    const source = defaultParams(params).comparisons
    if (source.length <= 1) return
    emit({ comparisons: source.filter((_, i) => i !== index) })
  }

  const emitActuality = (contract: JoinConsistencyParams['actualityDate']) => {
    emit({ actualityDate: contract })
  }

  // Map JOIN_CONSISTENCY-specific field errors to the shared component interface
  const actualityFieldErrors: ActualityDateFieldErrors | undefined = fieldErrors
    ? {
        leftAttribute: fieldErrors.actualityLeftAttribute,
        rightAttribute: fieldErrors.actualityRightAttribute,
        contractId: fieldErrors.contractId,
        toleranceSource: fieldErrors.toleranceSource,
        resolvedToleranceValue: fieldErrors.resolvedToleranceValue,
        resolvedToleranceUnit: fieldErrors.resolvedToleranceUnit,
        overrideToleranceValue: fieldErrors.overrideToleranceValue,
        overrideToleranceUnit: fieldErrors.overrideToleranceUnit,
      }
    : undefined

  const allDatasets = useMemo(() => {
    const productDatasets = filteredProducts.flatMap(product =>
      (product.datasets || []).map(dataset => ({
        scope: 'product' as const,
        productId: product.id,
        productName: product.name,
        dataset,
      })),
    )

    const standalone = standaloneDatasets.map(dataset => ({
      scope: 'standalone' as const,
      productId: '',
      productName: 'Standalone datasets',
      dataset,
    }))

    return [...productDatasets, ...standalone]
  }, [filteredProducts, standaloneDatasets])

  const findVersionPath = (versionId: string) => {
    const normalized = String(versionId || '').trim()
    if (!normalized) return null

    for (const entry of allDatasets) {
      for (const dataObject of entry.dataset.dataObjects || []) {
        const version = (dataObject.versions || []).find(item => item.id === normalized)
        if (version) {
          return {
            scope: entry.scope,
            productId: entry.productId,
            datasetId: entry.dataset.id,
            objectId: dataObject.id,
          }
        }
      }
    }

    return null
  }

  useEffect(() => {
    filteredProducts.forEach(product => {
      void loadDatasets(product.id)
    })
  }, [filteredProducts, loadDatasets])

  useEffect(() => {
    const path = findVersionPath(defaultParams(params).leftDataObjectVersionId)
    if (!path) return
    setLeftScope(path.scope)
    setLeftProductId(path.productId)
    setLeftDatasetId(path.datasetId)
    setLeftObjectId(path.objectId)
  }, [defaultParams(params).leftDataObjectVersionId, allDatasets])

  useEffect(() => {
    const path = findVersionPath(defaultParams(params).rightDataObjectVersionId)
    if (!path) return
    setRightScope(path.scope)
    setRightProductId(path.productId)
    setRightDatasetId(path.datasetId)
    setRightObjectId(path.objectId)
  }, [defaultParams(params).rightDataObjectVersionId, allDatasets])

  useEffect(() => {
    if (!leftDatasetId) return
    void loadDataObjects(leftDatasetId)
  }, [leftDatasetId, loadDataObjects])

  useEffect(() => {
    if (!rightDatasetId) return
    void loadDataObjects(rightDatasetId)
  }, [rightDatasetId, loadDataObjects])

  useEffect(() => {
    if (!leftObjectId) return
    void loadVersions(leftObjectId)
  }, [leftObjectId, loadVersions])

  useEffect(() => {
    if (!rightObjectId) return
    void loadVersions(rightObjectId)
  }, [rightObjectId, loadVersions])

  useEffect(() => {
    const leftVersionId = defaultParams(params).leftDataObjectVersionId
    if (leftVersionId) {
      void loadAttributes(leftVersionId)
    }
  }, [defaultParams(params).leftDataObjectVersionId, loadAttributes])

  useEffect(() => {
    const rightVersionId = defaultParams(params).rightDataObjectVersionId
    if (rightVersionId) {
      void loadAttributes(rightVersionId)
    }
  }, [defaultParams(params).rightDataObjectVersionId, loadAttributes])

  const selectedLeftDatasets = useMemo(() => {
    if (leftScope === 'standalone') {
      return standaloneDatasets
    }
    const product = filteredProducts.find(item => item.id === leftProductId)
    return product?.datasets || []
  }, [leftScope, standaloneDatasets, filteredProducts, leftProductId])

  const selectedRightDatasets = useMemo(() => {
    if (rightScope === 'standalone') {
      return standaloneDatasets
    }
    const product = filteredProducts.find(item => item.id === rightProductId)
    return product?.datasets || []
  }, [rightScope, standaloneDatasets, filteredProducts, rightProductId])

  const leftDataset = selectedLeftDatasets.find(item => item.id === leftDatasetId)
  const rightDataset = selectedRightDatasets.find(item => item.id === rightDatasetId)
  const leftObject = (leftDataset?.dataObjects || []).find(item => item.id === leftObjectId)
  const rightObject = (rightDataset?.dataObjects || []).find(item => item.id === rightObjectId)

  const withCurrentVersionOption = (versions: DataObjectVersion[], currentId: string) => {
    if (!currentId) {
      return versions
    }
    if (versions.some(item => item.id === currentId)) {
      return versions
    }
    return [
      {
        id: currentId,
        dataObjectId: '',
        version: -1,
        createdAt: '',
        schemaHash: '',
        attributes: [],
      },
      ...versions,
    ]
  }

  const leftVersions = withCurrentVersionOption(leftObject?.versions || [], defaultParams(params).leftDataObjectVersionId)
  const rightVersions = withCurrentVersionOption(rightObject?.versions || [], defaultParams(params).rightDataObjectVersionId)

  const findVersionInCatalog = (versionId: string): DataObjectVersion | null => {
    const normalized = String(versionId || '').trim()
    if (!normalized) {
      return null
    }

    for (const entry of allDatasets) {
      for (const dataObject of entry.dataset.dataObjects || []) {
        const version = (dataObject.versions || []).find(item => item.id === normalized)
        if (version) {
          return version
        }
      }
    }

    return null
  }

  const leftVersion = findVersionInCatalog(defaultParams(params).leftDataObjectVersionId)
  const rightVersion = findVersionInCatalog(defaultParams(params).rightDataObjectVersionId)
  const leftAttributes = leftVersion?.attributes || []
  const rightAttributes = rightVersion?.attributes || []

  const withCurrentAttributeOption = (attributes: DataAttribute[], currentName: string) => {
    const normalized = String(currentName || '').trim()
    if (!normalized) {
      return attributes
    }
    if (attributes.some(attr => attr.name === normalized)) {
      return attributes
    }
    return [
      {
        id: `current-${normalized}`,
        name: normalized,
        type: 'string',
        nullable: true,
      },
      ...attributes,
    ]
  }

  const formatVersionLabel = (version: DataObjectVersion) => {
    if (version.version < 0) {
      return `${version.id} (current value, not loaded)`
    }
    const suffix = version.createdAt ? ` - ${new Date(version.createdAt).toLocaleDateString()}` : ''
    return `v${version.version}${suffix}`
  }

  const renderDatasetOptions = (datasets: DataSet[]) => {
    return datasets.map(dataset => (
      <option key={dataset.id} value={dataset.id}>
        {dataset.name}
      </option>
    ))
  }

  const renderObjectOptions = (objects: DataObject[]) => {
    return objects.map(dataObject => (
      <option key={dataObject.id} value={dataObject.id}>
        {dataObject.name}
      </option>
    ))
  }

  const renderVersionOptions = (versions: DataObjectVersion[]) => {
    return versions.map(version => (
      <option key={version.id} value={version.id}>
        {formatVersionLabel(version)}
      </option>
    ))
  }

  const renderAttributeOptions = (attributes: DataAttribute[], currentName: string) => {
    return withCurrentAttributeOption(attributes, currentName).map(attr => (
      <option key={attr.id} value={attr.name}>
        {attr.name}
      </option>
    ))
  }

  return (
    <div className="check-type-form join-consistency-form">
      <div className="join-consistency-section">
        <label className="check-type-form-label">Catalog-backed object version selectors</label>

        <div className="join-consistency-catalog-title">Left side</div>
        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-jc-left-scope">Dataset scope</label>
            <select
              id="ct-jc-left-scope"
              className="modal-input"
              value={leftScope}
              onChange={(e) => {
                const nextScope = e.target.value === 'standalone' ? 'standalone' : 'product'
                setLeftScope(nextScope)
                setLeftProductId('')
                setLeftDatasetId('')
                setLeftObjectId('')
                emit({ leftDataObjectVersionId: '' })
              }}
            >
              <option value="product">Product datasets</option>
              <option value="standalone">Standalone datasets</option>
            </select>
          </div>
          {leftScope === 'product' && (
            <div className="check-type-form-field check-type-form-field--half">
              <label className="check-type-form-label" htmlFor="ct-jc-left-product">Product</label>
              <select
                id="ct-jc-left-product"
                className="modal-input"
                value={leftProductId}
                onChange={(e) => {
                  const productId = e.target.value
                  setLeftProductId(productId)
                  setLeftDatasetId('')
                  setLeftObjectId('')
                  emit({ leftDataObjectVersionId: '' })
                  if (productId) {
                    void loadDatasets(productId)
                  }
                }}
              >
                <option value="">Select product</option>
                {filteredProducts.map(product => (
                  <option key={product.id} value={product.id}>
                    {product.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-jc-left-dataset">Dataset</label>
            <select
              id="ct-jc-left-dataset"
              className="modal-input"
              value={leftDatasetId}
              onChange={(e) => {
                const datasetId = e.target.value
                setLeftDatasetId(datasetId)
                setLeftObjectId('')
                emit({ leftDataObjectVersionId: '' })
                if (datasetId) {
                  void loadDataObjects(datasetId)
                }
              }}
            >
              <option value="">Select dataset</option>
              {renderDatasetOptions(selectedLeftDatasets)}
            </select>
          </div>
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-jc-left-object">Data object</label>
            <select
              id="ct-jc-left-object"
              className="modal-input"
              value={leftObjectId}
              onChange={(e) => {
                const objectId = e.target.value
                setLeftObjectId(objectId)
                emit({ leftDataObjectVersionId: '' })
                if (objectId) {
                  void loadVersions(objectId)
                }
              }}
            >
              <option value="">Select object</option>
              {renderObjectOptions(leftDataset?.dataObjects || [])}
            </select>
          </div>
        </div>

        <div className="check-type-form-row">
          <div className="check-type-form-field">
            <label className="check-type-form-label" htmlFor="ct-jc-left-version">Left data object version</label>
            <select
              id="ct-jc-left-version"
              className="modal-input"
              value={defaultParams(params).leftDataObjectVersionId}
              onChange={(e) => emit({ leftDataObjectVersionId: e.target.value })}
            >
              <option value="">Select left version</option>
              {renderVersionOptions(leftVersions)}
            </select>
            {fieldErrors?.leftDataObjectVersionId && (
              <p className="check-type-form-hint join-consistency-field-error">{fieldErrors.leftDataObjectVersionId}</p>
            )}
          </div>
        </div>

        <div className="join-consistency-catalog-title">Right side</div>
        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-jc-right-scope">Dataset scope</label>
            <select
              id="ct-jc-right-scope"
              className="modal-input"
              value={rightScope}
              onChange={(e) => {
                const nextScope = e.target.value === 'standalone' ? 'standalone' : 'product'
                setRightScope(nextScope)
                setRightProductId('')
                setRightDatasetId('')
                setRightObjectId('')
                emit({ rightDataObjectVersionId: '' })
              }}
            >
              <option value="product">Product datasets</option>
              <option value="standalone">Standalone datasets</option>
            </select>
          </div>
          {rightScope === 'product' && (
            <div className="check-type-form-field check-type-form-field--half">
              <label className="check-type-form-label" htmlFor="ct-jc-right-product">Product</label>
              <select
                id="ct-jc-right-product"
                className="modal-input"
                value={rightProductId}
                onChange={(e) => {
                  const productId = e.target.value
                  setRightProductId(productId)
                  setRightDatasetId('')
                  setRightObjectId('')
                  emit({ rightDataObjectVersionId: '' })
                  if (productId) {
                    void loadDatasets(productId)
                  }
                }}
              >
                <option value="">Select product</option>
                {filteredProducts.map(product => (
                  <option key={product.id} value={product.id}>
                    {product.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-jc-right-dataset">Dataset</label>
            <select
              id="ct-jc-right-dataset"
              className="modal-input"
              value={rightDatasetId}
              onChange={(e) => {
                const datasetId = e.target.value
                setRightDatasetId(datasetId)
                setRightObjectId('')
                emit({ rightDataObjectVersionId: '' })
                if (datasetId) {
                  void loadDataObjects(datasetId)
                }
              }}
            >
              <option value="">Select dataset</option>
              {renderDatasetOptions(selectedRightDatasets)}
            </select>
          </div>
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-jc-right-object">Data object</label>
            <select
              id="ct-jc-right-object"
              className="modal-input"
              value={rightObjectId}
              onChange={(e) => {
                const objectId = e.target.value
                setRightObjectId(objectId)
                emit({ rightDataObjectVersionId: '' })
                if (objectId) {
                  void loadVersions(objectId)
                }
              }}
            >
              <option value="">Select object</option>
              {renderObjectOptions(rightDataset?.dataObjects || [])}
            </select>
          </div>
        </div>

        <div className="check-type-form-row">
          <div className="check-type-form-field">
            <label className="check-type-form-label" htmlFor="ct-jc-right-version">Right data object version</label>
            <select
              id="ct-jc-right-version"
              className="modal-input"
              value={defaultParams(params).rightDataObjectVersionId}
              onChange={(e) => emit({ rightDataObjectVersionId: e.target.value })}
            >
              <option value="">Select right version</option>
              {renderVersionOptions(rightVersions)}
            </select>
            {fieldErrors?.rightDataObjectVersionId && (
              <p className="check-type-form-hint join-consistency-field-error">{fieldErrors.rightDataObjectVersionId}</p>
            )}
          </div>
        </div>
      </div>

      <div className="join-consistency-section">
        <div className="join-consistency-header-row">
          <label className="check-type-form-label">Join keys</label>
          <button type="button" className="btn btn-secondary" onClick={addJoinKey}>
            + Add key
          </button>
        </div>
        {defaultParams(params).joinKeys.map((joinKey, index) => (
          <div className="check-type-form-row" key={`join-key-${index}`}>
            <div className="check-type-form-field check-type-form-field--half">
              <select
                className="modal-input"
                value={joinKey.leftAttribute}
                onChange={(e) => updateJoinKey(index, 'leftAttribute', e.target.value)}
              >
                <option value="">Select left attribute</option>
                {renderAttributeOptions(leftAttributes, joinKey.leftAttribute)}
              </select>
            </div>
            <div className="check-type-form-field check-type-form-field--half">
              <div className="join-consistency-inline-input">
                <select
                  className="modal-input"
                  value={joinKey.rightAttribute}
                  onChange={(e) => updateJoinKey(index, 'rightAttribute', e.target.value)}
                >
                  <option value="">Select right attribute</option>
                  {renderAttributeOptions(rightAttributes, joinKey.rightAttribute)}
                </select>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => removeJoinKey(index)}
                  disabled={defaultParams(params).joinKeys.length <= 1}
                  title="Remove join key"
                >
                  Remove
                </button>
              </div>
            </div>
          </div>
        ))}
        {fieldErrors?.joinKeys && (
          <p className="check-type-form-hint join-consistency-field-error">{fieldErrors.joinKeys}</p>
        )}
      </div>

      <div className="join-consistency-section">
        <div className="join-consistency-header-row">
          <label className="check-type-form-label">Comparison pairs</label>
          <button type="button" className="btn btn-secondary" onClick={addComparison}>
            + Add comparison
          </button>
        </div>
        {defaultParams(params).comparisons.map((comparison, index) => (
          <div className="check-type-form-row" key={`comparison-${index}`}>
            <div className="check-type-form-field check-type-form-field--half">
              <select
                className="modal-input"
                value={comparison.leftAttribute}
                onChange={(e) => updateComparison(index, 'leftAttribute', e.target.value)}
              >
                <option value="">Select left attribute</option>
                {renderAttributeOptions(leftAttributes, comparison.leftAttribute)}
              </select>
            </div>
            <div className="check-type-form-field check-type-form-field--half">
              <select
                className="modal-input"
                value={comparison.rightAttribute}
                onChange={(e) => updateComparison(index, 'rightAttribute', e.target.value)}
              >
                <option value="">Select right attribute</option>
                {renderAttributeOptions(rightAttributes, comparison.rightAttribute)}
              </select>
            </div>
            <div className="check-type-form-field join-consistency-mode-field">
              <AppSelect
                id={`ct-jc-mode-${index}`}
                label="Mode"
                value={comparison.mode}
                onChange={(value) => updateComparison(index, 'mode', String(value || 'exact'))}
                options={[
                  { value: 'exact', label: 'Exact' },
                  { value: 'case_insensitive', label: 'Case insensitive' },
                ]}
              />
            </div>
            <div className="check-type-form-field join-consistency-remove-field">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => removeComparison(index)}
                disabled={defaultParams(params).comparisons.length <= 1}
                title="Remove comparison"
              >
                Remove
              </button>
            </div>
          </div>
        ))}
        {fieldErrors?.comparisons && (
          <p className="check-type-form-hint join-consistency-field-error">{fieldErrors.comparisons}</p>
        )}
      </div>

      <div className="join-consistency-section">
        <ActualityDateConfig
          value={defaultParams(params).actualityDate}
          onChange={(contract) => emitActuality(contract)}
          leftAttributes={leftAttributes.map((attr) => attr.name)}
          rightAttributes={rightAttributes.map((attr) => attr.name)}
          fieldErrors={actualityFieldErrors}
          idPrefix="ct-jc-actuality"
        />
      </div>

      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-jc-min-match-rate">
            Minimum match rate (0-100)
          </label>
          <input
            id="ct-jc-min-match-rate"
            type="number"
            className="modal-input"
            min={0}
            max={100}
            step={0.1}
            value={defaultParams(params).minMatchRate}
            onChange={(e) => emit({ minMatchRate: Number(e.target.value) || 0 })}
          />
        </div>
      </div>

      <p className="check-type-form-hint">
        Resolved tolerance fields are populated by the backend contract resolver during create/update.
      </p>
    </div>
  )
}
