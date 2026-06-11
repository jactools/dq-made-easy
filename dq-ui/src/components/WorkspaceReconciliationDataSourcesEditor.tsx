import React from 'react'
import { Button, SecondaryButton } from './Button'
import { WorkspaceReconciliationDataSource } from '../types/settings'

interface WorkspaceReconciliationDataSourcesEditorProps {
  value: WorkspaceReconciliationDataSource[]
  allowedSourceTypes: string[]
  disabled?: boolean
  onChange: (value: WorkspaceReconciliationDataSource[]) => void
}

const DEFAULT_CONNECTION_PARAMETERS = '{\n  "host": "",\n  "port": ""\n}'

const createDatasource = (index: number, allowedSourceTypes: string[]): WorkspaceReconciliationDataSource => ({
  id: `recon-datasource-${Date.now()}-${index}`,
  name: `Datasource ${index + 1}`,
  sourceType: allowedSourceTypes[0] || 'adls',
  connectionString: '',
  connectionParameters: DEFAULT_CONNECTION_PARAMETERS,
  description: '',
  updatedAt: new Date().toISOString(),
})

const normalizeDatasource = (
  datasource: WorkspaceReconciliationDataSource,
  allowedSourceTypes: string[],
): WorkspaceReconciliationDataSource => {
  const sourceType = datasource.sourceType || allowedSourceTypes[0] || 'adls'
  return {
    ...datasource,
    name: datasource.name || 'Datasource',
    sourceType,
    connectionString: datasource.connectionString || '',
    connectionParameters: datasource.connectionParameters || DEFAULT_CONNECTION_PARAMETERS,
    description: datasource.description || '',
    updatedAt: new Date().toISOString(),
  }
}

export const WorkspaceReconciliationDataSourcesEditor: React.FC<WorkspaceReconciliationDataSourcesEditorProps> = ({
  value,
  allowedSourceTypes,
  disabled = false,
  onChange,
}) => {
  const datasources = Array.isArray(value) ? value : []

  const updateDatasource = (index: number, patch: Partial<WorkspaceReconciliationDataSource>) => {
    onChange(
      datasources.map((datasource, datasourceIndex) =>
        datasourceIndex === index
          ? normalizeDatasource({ ...datasource, ...patch }, allowedSourceTypes)
          : datasource,
      ),
    )
  }

  const addDatasource = () => {
    onChange([...datasources, createDatasource(datasources.length, allowedSourceTypes)])
  }

  const removeDatasource = (index: number) => {
    onChange(datasources.filter((_, datasourceIndex) => datasourceIndex !== index))
  }

  return (
    <div className="workspace-reconciliation-datasources-editor">
      <div className="settings-inline-header">
        <div>
          <h4>Reconciliation datasources</h4>
          <p className="settings-hint">
            Workspace admins can register source connections for the reconciliation hub. Use only the datasource types
            enabled by the app admin.
          </p>
        </div>
        <Button type="button" onClick={addDatasource} disabled={disabled}>
          Add datasource
        </Button>
      </div>

      {allowedSourceTypes.length > 0 && (
        <p className="settings-hint">
          Allowed source types: {allowedSourceTypes.join(', ')}
        </p>
      )}

      {datasources.length === 0 ? (
        <div className="settings-empty-state">
          <p>No reconciliation datasources have been configured yet.</p>
        </div>
      ) : (
        <div className="workspace-reconciliation-datasources-list">
          {datasources.map((datasource, index) => {
            const sourceTypeValue = datasource.sourceType || allowedSourceTypes[0] || ''
            const sourceTypeAllowed = allowedSourceTypes.length === 0 || allowedSourceTypes.includes(sourceTypeValue)

            return (
              <section key={datasource.id || `${index}`} className="workspace-reconciliation-datasource-card">
                <div className="form-grid form-grid-two-col">
                  <div className="form-group">
                    <label htmlFor={`recon-datasource-name-${index}`}>Name</label>
                    <input
                      id={`recon-datasource-name-${index}`}
                      type="text"
                      value={datasource.name}
                      disabled={disabled}
                      onChange={(event) => updateDatasource(index, { name: event.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor={`recon-datasource-type-${index}`}>Source type</label>
                    {allowedSourceTypes.length > 0 ? (
                      <select
                        id={`recon-datasource-type-${index}`}
                        value={sourceTypeValue}
                        disabled={disabled}
                        onChange={(event) => updateDatasource(index, { sourceType: event.target.value })}
                      >
                        {allowedSourceTypes.map((sourceType) => (
                          <option key={sourceType} value={sourceType}>
                            {sourceType}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={`recon-datasource-type-${index}`}
                        type="text"
                        value={sourceTypeValue}
                        disabled={disabled}
                        onChange={(event) => updateDatasource(index, { sourceType: event.target.value })}
                      />
                    )}
                    {!sourceTypeAllowed && <p className="settings-error-text">This source type is not allowed.</p>}
                  </div>
                </div>

                <div className="form-grid form-grid-two-col">
                  <div className="form-group">
                    <label htmlFor={`recon-datasource-connection-${index}`}>Connection string</label>
                    <input
                      id={`recon-datasource-connection-${index}`}
                      type="text"
                      value={datasource.connectionString || ''}
                      disabled={disabled}
                      onChange={(event) => updateDatasource(index, { connectionString: event.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor={`recon-datasource-description-${index}`}>Description</label>
                    <input
                      id={`recon-datasource-description-${index}`}
                      type="text"
                      value={datasource.description || ''}
                      disabled={disabled}
                      onChange={(event) => updateDatasource(index, { description: event.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor={`recon-datasource-parameters-${index}`}>Connection parameters</label>
                  <textarea
                    id={`recon-datasource-parameters-${index}`}
                    value={datasource.connectionParameters || DEFAULT_CONNECTION_PARAMETERS}
                    disabled={disabled}
                    rows={5}
                    onChange={(event) => updateDatasource(index, { connectionParameters: event.target.value })}
                  />
                  <p className="settings-hint">
                    Store JSON payload details here, such as endpoints, credentials references, and container names.
                  </p>
                </div>

                <div className="settings-inline-actions">
                  <SecondaryButton type="button" onClick={() => removeDatasource(index)} disabled={disabled}>
                    Remove datasource
                  </SecondaryButton>
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
