import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth, useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import { Button, SecondaryButton } from './Button'
import { AppTable } from './app-primitives'
import { getWorkspaceDisplayName } from './WorkspaceSelector'
import './DeliveryInventory.css'

type DeliveryInventoryRow = {
  id: string
  dataObjectVersionId?: string | null
  version?: number | null
  deliveredAt: string
  deliveryLocation?: string | null
  storageExists: boolean
  storageObjectCount: number
}

type DeliveryInventoryNote = {
  id: string
  dataDeliveryId: string
  dataObjectId: string
  dataObjectVersionId?: string | null
  version: number
  deliveredAt: string
  timestamp: string
  deliveryLocation?: string | null
  deliveryStatus: string
  deliveryFormat?: string | null
  deliveryFormatWarning?: string | null
  objectStorageClassification?: string | null
  evidenceClassification?: string | null
  recordCount: number
  sizeBytes: number
  attributesCount: number
  fileCount?: number | null
  fileNames?: string[] | null
  storageExists?: boolean | null
  storageObjectCount?: number | null
  ingestorName?: string | null
  ingestorRunId?: string | null
  sourceSystem?: string | null
  sourceSnapshotId?: string | null
  checksum?: string | null
  checksumAlgorithm?: string | null
  metadataJson?: Record<string, unknown> | null
}

type DeliveryInventoryPage = {
  data: DeliveryInventoryRow[]
  pagination: {
    total: number
    page: number
    limit: number
    totalPages: number
    hasNext: boolean
    hasPrevious: boolean
  }
}

export const DeliveryInventory: React.FC = () => {
  const auth = useAuth()
  const settings = useSettings()
  const [rows, setRows] = useState<DeliveryInventoryRow[]>([])
  const [pagination, setPagination] = useState<DeliveryInventoryPage['pagination'] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedDeliveryId, setSelectedDeliveryId] = useState<string | null>(null)
  const [selectedDeliveryNote, setSelectedDeliveryNote] = useState<DeliveryInventoryNote | null>(null)
  const [selectedDeliveryNoteLoading, setSelectedDeliveryNoteLoading] = useState(false)
  const [selectedDeliveryNoteLoadingMode, setSelectedDeliveryNoteLoadingMode] = useState<'note' | 'storage' | null>(null)
  const [selectedDeliveryNoteError, setSelectedDeliveryNoteError] = useState<string | null>(null)
  const [objectStorageClassification, setObjectStorageClassification] = useState<string>('')
  const [evidenceClassification, setEvidenceClassification] = useState<string>('')
  const selectedDeliveryNoteRequestId = useRef(0)

  const workspaceId = auth.currentWorkspaceId
  const canViewInventory = Boolean(
    auth.isAuthenticated
    && workspaceId
    && auth.hasAnyScope(['dq:data_catalog:read', 'dq:data_catalog:*', 'dq:*'])
  )
  const apiBase = toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl)

  const loadInventory = useCallback(async () => {
    if (!canViewInventory) {
      setRows([])
      setPagination(null)
      setLoading(false)
      setError(null)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const token = getAuthToken()
      const params = new URLSearchParams()
      params.set('workspace', workspaceId as string)
      params.set('page', '1')
      params.set('limit', '100')
      if (objectStorageClassification) {
        params.set('objectStorageClassification', objectStorageClassification)
      }
      if (evidenceClassification) {
        params.set('evidenceClassification', evidenceClassification)
      }
      const response = await fetch(`${apiBase}/delivery-inventory?${params.toString()}`,
        {
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        },
      )

      if (!response.ok) {
        throw new Error(`Unable to load delivery inventory (${response.status}).`)
      }

      const payload = snakeToCamel<DeliveryInventoryPage>(await response.json())
      setRows(Array.isArray(payload.data) ? payload.data : [])
      setPagination(payload.pagination ?? null)
    } catch (loadError) {
      setRows([])
      setPagination(null)
      setError(loadError instanceof Error ? loadError.message : 'Unable to load delivery inventory.')
    } finally {
      setLoading(false)
    }
  }, [apiBase, canViewInventory, workspaceId])

  useEffect(() => {
    void loadInventory()
  }, [loadInventory])

  const filteredRows = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) {
      return rows
    }

    return rows.filter((row) => (
      row.id.toLowerCase().includes(query)
      || String(row.deliveryLocation || '').toLowerCase().includes(query)
      || String(row.dataObjectVersionId || '').toLowerCase().includes(query)
      || String(row.version || '').toLowerCase().includes(query)
    ))
  }, [rows, searchQuery])

  const selectedDelivery = useMemo(
    () => rows.find((row) => row.id === selectedDeliveryId) ?? null,
    [rows, selectedDeliveryId],
  )

  useEffect(() => {
    if (!selectedDeliveryId) {
      return
    }

    if (rows.some((row) => row.id === selectedDeliveryId)) {
      return
    }

    setSelectedDeliveryId(null)
    setSelectedDeliveryNote(null)
    setSelectedDeliveryNoteError(null)
    setSelectedDeliveryNoteLoading(false)
    setSelectedDeliveryNoteLoadingMode(null)
  }, [rows, selectedDeliveryId])

  const loadDeliveryNote = useCallback(async (deliveryId: string, includeStorageDetails = false) => {
    const requestId = selectedDeliveryNoteRequestId.current + 1
    selectedDeliveryNoteRequestId.current = requestId

    setSelectedDeliveryId(deliveryId)
    setSelectedDeliveryNoteError(null)
    setSelectedDeliveryNoteLoading(true)
    setSelectedDeliveryNoteLoadingMode(includeStorageDetails ? 'storage' : 'note')
    if (!includeStorageDetails) {
      setSelectedDeliveryNote(null)
    }

    try {
      const token = getAuthToken()
      const params = includeStorageDetails ? '?include_storage_details=true' : ''
      const response = await fetch(`${apiBase}/data-deliveries/${encodeURIComponent(deliveryId)}/note${params}`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })

      if (!response.ok) {
        throw new Error(`Unable to load delivery note (${response.status}).`)
      }

      const payload = snakeToCamel<DeliveryInventoryNote>(await response.json())
      if (selectedDeliveryNoteRequestId.current !== requestId) {
        return
      }

      setSelectedDeliveryNote(payload)
    } catch (loadError) {
      if (selectedDeliveryNoteRequestId.current !== requestId) {
        return
      }

      setSelectedDeliveryNote(null)
      setSelectedDeliveryNoteError(
        loadError instanceof Error ? loadError.message : 'Unable to load delivery note.',
      )
    } finally {
      if (selectedDeliveryNoteRequestId.current === requestId) {
        setSelectedDeliveryNoteLoading(false)
        setSelectedDeliveryNoteLoadingMode(null)
      }
    }
  }, [apiBase])

  const renderDetailField = (label: string, value: string | number | null | undefined) => (
    <div className="delivery-inventory-detail-field">
      <span>{label}</span>
      <strong>{value === null || value === undefined || value === '' ? 'Unavailable' : value}</strong>
    </div>
  )

  const renderMetadataJson = (metadataJson: Record<string, unknown> | null | undefined) => {
    if (!metadataJson || Object.keys(metadataJson).length === 0) {
      return <div className="delivery-inventory-empty-note">No metadata captured for this delivery note.</div>
    }

    return <pre className="delivery-inventory-json">{JSON.stringify(metadataJson, null, 2)}</pre>
  }

  const storagePresentCount = rows.filter((row) => row.storageExists).length
  const storageMissingCount = rows.length - storagePresentCount
  const workspaceName = workspaceId ? getWorkspaceDisplayName(workspaceId) : 'No workspace selected'

  if (!auth.isAuthenticated) {
    return null
  }

  if (!workspaceId) {
    return (
      <section className="delivery-inventory-page">
        <div className="delivery-inventory-empty-state">
          <h2>Select a workspace</h2>
          <p>Choose a workspace to inspect its deliveries and storage presence.</p>
        </div>
      </section>
    )
  }

  if (!auth.hasAnyScope(['dq:data_catalog:read', 'dq:data_catalog:*', 'dq:*'])) {
    return (
      <section className="delivery-inventory-page">
        <div className="delivery-inventory-empty-state">
          <h2>Access restricted</h2>
          <p>This view is available only to users with data catalog read access in the active workspace.</p>
        </div>
      </section>
    )
  }

  return (
    <section className="delivery-inventory-page">
      <header className="delivery-inventory-header">
        <div>
          <p className="delivery-inventory-kicker">Workspace inventory</p>
          <h2>Deliveries in {workspaceName}</h2>
          <p className="delivery-inventory-subtitle">
            Delivery rows from the catalog, with AIStor presence checks and object counts only.
          </p>
        </div>
        <div className="delivery-inventory-actions">
          <SecondaryButton onClick={() => void loadInventory()} disabled={loading}>
            Refresh
          </SecondaryButton>
        </div>
      </header>

      <div className="delivery-inventory-summary">
        <div className="delivery-inventory-summary-card">
          <span className="summary-label">Deliveries</span>
          <span className="summary-value">{pagination?.total ?? rows.length}</span>
        </div>
        <div className="delivery-inventory-summary-card">
          <span className="summary-label">On storage</span>
          <span className="summary-value">{storagePresentCount}</span>
        </div>
        <div className="delivery-inventory-summary-card">
          <span className="summary-label">Missing storage</span>
          <span className="summary-value">{storageMissingCount}</span>
        </div>
      </div>

      <div className="delivery-inventory-toolbar">
        <label className="delivery-inventory-search">
          <span>Search delivery id or location</span>
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Filter deliveries"
          />
        </label>
        <div className="delivery-inventory-classification-filters">
          <label className="delivery-inventory-filter-label">
            <span>Storage classification</span>
            <select
              value={objectStorageClassification}
              onChange={(event) => setObjectStorageClassification(event.target.value)}
            >
              <option value="">All</option>
              <option value="synthetic_test">synthetic_test</option>
              <option value="real_evidence">real_evidence</option>
            </select>
          </label>
          <label className="delivery-inventory-filter-label">
            <span>Evidence classification</span>
            <select
              value={evidenceClassification}
              onChange={(event) => setEvidenceClassification(event.target.value)}
            >
              <option value="">All</option>
              <option value="synthetic_result">synthetic_result</option>
              <option value="real_evidence">real_evidence</option>
            </select>
          </label>
        </div>
        <div className="delivery-inventory-toolbar-actions">
          <Button variant="tertiary" onClick={() => setSearchQuery('')} disabled={!searchQuery}>
            Clear search
          </Button>
          <Button
            variant="tertiary"
            onClick={() => {
              setObjectStorageClassification('')
              setEvidenceClassification('')
            }}
            disabled={!objectStorageClassification && !evidenceClassification}
          >
            Clear filters
          </Button>
        </div>
      </div>

      {loading && (
        <div className="delivery-inventory-state">Loading delivery inventory...</div>
      )}

      {error && !loading && (
        <div className="delivery-inventory-state delivery-inventory-error">
          {error}
        </div>
      )}

      {!loading && !error && (
        <div className="delivery-inventory-body">
          <div className="delivery-inventory-table-card">
            {filteredRows.length === 0 ? (
              <div className="delivery-inventory-empty-state compact">
                <h3>No deliveries match this view</h3>
                <p>There are no delivery rows for the selected workspace, or the current search filter is too narrow.</p>
              </div>
            ) : (
              <AppTable className="delivery-inventory-table">
                <thead>
                  <tr>
                    <th>Delivery ID</th>
                    <th>Delivery Location</th>
                    <th>Files</th>
                    <th>Storage</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((row) => (
                    <tr key={row.id} className={selectedDeliveryId === row.id ? 'selected' : ''} aria-selected={selectedDeliveryId === row.id}>
                      <td>
                        <div className="delivery-id-cell">
                          <strong>{row.id}</strong>
                          {row.version !== null && row.version !== undefined ? (
                            <span>V{row.version}</span>
                          ) : row.dataObjectVersionId ? (
                            <span>{row.dataObjectVersionId}</span>
                          ) : null}
                        </div>
                      </td>
                      <td className="delivery-location-cell">{row.deliveryLocation || 'Unavailable'}</td>
                      <td>{row.storageObjectCount.toLocaleString()}</td>
                      <td>
                        <span className={`delivery-storage-badge ${row.storageExists ? 'present' : 'missing'}`}>
                          {row.storageExists ? 'Present on AIStor' : 'Missing on AIStor'}
                        </span>
                      </td>
                      <td>
                        <div className="delivery-note-actions">
                          <SecondaryButton
                            onClick={() => void loadDeliveryNote(row.id)}
                            disabled={selectedDeliveryNoteLoading && selectedDeliveryId === row.id}
                          >
                            {selectedDeliveryNoteLoading && selectedDeliveryId === row.id && selectedDeliveryNoteLoadingMode === 'note'
                              ? 'Loading...'
                              : 'View note'}
                          </SecondaryButton>
                          <SecondaryButton
                            onClick={() => void loadDeliveryNote(row.id, true)}
                            disabled={selectedDeliveryNoteLoading && selectedDeliveryId === row.id}
                          >
                            {selectedDeliveryNoteLoading && selectedDeliveryId === row.id && selectedDeliveryNoteLoadingMode === 'storage'
                              ? 'Loading storage...'
                              : selectedDeliveryNote?.id === `note-${row.id}` && selectedDeliveryNote.storageExists != null
                                ? 'Refresh storage details'
                                : 'Load storage details'}
                          </SecondaryButton>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </AppTable>
            )}
          </div>

          <aside className="delivery-inventory-detail-panel" aria-live="polite">
            <div className="delivery-inventory-detail-header">
              <div>
                <p className="delivery-inventory-kicker">Delivery note</p>
                <h3>{selectedDelivery ? selectedDelivery.id : 'Select a delivery'}</h3>
                <p className="delivery-inventory-subtitle">
                  {selectedDelivery
                    ? 'Persistent note stored in data_delivery_notes and rendered without storage access.'
                    : 'Choose a delivery row to inspect the persisted note.'}
                </p>
              </div>
              {selectedDelivery && (
                <span className={`delivery-storage-badge ${selectedDelivery.storageExists ? 'present' : 'missing'}`}>
                  {selectedDelivery.storageExists ? 'On AIStor' : 'Missing on AIStor'}
                </span>
              )}
            </div>

            {!selectedDelivery && (
              <div className="delivery-inventory-empty-state compact">
                <h3>No delivery selected</h3>
                <p>Click View note for a delivery row to load the persisted delivery note.</p>
              </div>
            )}

            {selectedDelivery && selectedDeliveryNoteLoading && (
              <div className="delivery-inventory-state compact">Loading delivery note...</div>
            )}

            {selectedDelivery && selectedDeliveryNoteError && (
              <div className="delivery-inventory-state delivery-inventory-error">
                {selectedDeliveryNoteError}
              </div>
            )}

            {selectedDelivery && selectedDeliveryNote && (
              <>
                {selectedDeliveryNote.deliveryFormatWarning && (
                  <div className="delivery-inventory-warning" role="status">
                    {selectedDeliveryNote.deliveryFormatWarning}
                  </div>
                )}

                <div className="delivery-inventory-detail-grid">
                  {renderDetailField('Delivery ID', selectedDeliveryNote.dataDeliveryId)}
                  {renderDetailField('Delivery status', selectedDeliveryNote.deliveryStatus)}
                  {renderDetailField('Delivery format', selectedDeliveryNote.deliveryFormat)}
                  {renderDetailField('Object version', selectedDeliveryNote.version)}
                  {renderDetailField('Files', selectedDeliveryNote.fileCount)}
                  {renderDetailField('Records', selectedDeliveryNote.recordCount.toLocaleString())}
                  {renderDetailField('Size bytes', selectedDeliveryNote.sizeBytes.toLocaleString())}
                  {renderDetailField('Checksum', selectedDeliveryNote.checksum)}
                  {renderDetailField('Checksum algorithm', selectedDeliveryNote.checksumAlgorithm)}
                  {renderDetailField('Ingestor', selectedDeliveryNote.ingestorName)}
                  {renderDetailField('Ingestor run', selectedDeliveryNote.ingestorRunId)}
                  {renderDetailField('Source system', selectedDeliveryNote.sourceSystem)}
                </div>

                {(selectedDeliveryNote.storageExists != null
                  || selectedDeliveryNote.storageObjectCount != null
                  || selectedDeliveryNote.fileNames != null
                ) && (
                  <section className="delivery-inventory-detail-section">
                    <div className="delivery-inventory-detail-section-header">
                      <span>Storage details</span>
                      <strong>{selectedDeliveryNote.storageExists ? 'Present on storage' : 'Missing on storage'}</strong>
                    </div>
                    <div className="delivery-inventory-detail-grid storage-details-grid">
                      {renderDetailField('Storage object count', selectedDeliveryNote.storageObjectCount)}
                      {renderDetailField('Storage file names', selectedDeliveryNote.fileNames?.join(', '))}
                    </div>
                  </section>
                )}

                <section className="delivery-inventory-detail-section">
                  <div className="delivery-inventory-detail-section-header">
                    <span>Delivery location</span>
                    <strong>{selectedDeliveryNote.deliveryLocation || 'Unavailable'}</strong>
                  </div>
                </section>

                <section className="delivery-inventory-detail-section">
                  <div className="delivery-inventory-detail-section-header">
                    <span>Metadata</span>
                    <strong>{selectedDeliveryNote.sourceSnapshotId || 'Unavailable'}</strong>
                  </div>
                  {renderMetadataJson(selectedDeliveryNote.metadataJson)}
                </section>
              </>
            )}
          </aside>
        </div>
      )}
    </section>
  )
}