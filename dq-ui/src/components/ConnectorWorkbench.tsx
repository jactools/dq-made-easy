import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth, useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import {
  AppBadge,
  AppEmptyState,
  AppPageHeader,
  AppPageShell,
  AppPanel,
  AppSelect,
  AppTabs,
  AppInput,
  AppTextarea,
} from './app-primitives'
import { PrimaryButton, SecondaryButton, TertiaryButton } from './Button'
import { AgentChatPanel } from './AgentChatPanel'
import './ConnectorWorkbench.css'

type ConnectorProvider = 'postgresql' | 'sql_server' | 'external_api' | 'azure_adls' | 's3_blob'
type ConnectorTab = 'setup' | 'validation' | 'sync'

type ConnectorErrorView = {
  kind: string
  message: string
  code?: string | null
  field?: string | null
  retryable?: boolean
  details?: Record<string, unknown>
}

type ConnectorDiscoveryItemView = {
  identifier: string
  kind: string
  name?: string | null
  workspaceId?: string | null
  metadata?: Record<string, unknown>
}

type ConnectorDiscoveryResultView = {
  provider: ConnectorProvider
  items: ConnectorDiscoveryItemView[]
  errors: ConnectorErrorView[]
}

type ConnectorHealthResultView = {
  provider: ConnectorProvider
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown'
  details: Record<string, unknown>
  errors: ConnectorErrorView[]
}

type ConnectorSyncResultView = {
  provider: ConnectorProvider
  syncedCount: number
  items: ConnectorDiscoveryItemView[]
  errors: ConnectorErrorView[]
}

type ConnectorSyncJobView = {
  completedAt: string
  syncedCount: number
  result: ConnectorSyncResultView
  correlationId: string
}
type ConnectorSyncStatusModelView = {
  entity: string
  statuses: Array<{
    value: string
    label: string
    description?: string | null
    isInitial: boolean
    isTerminal: boolean
  }>
  transitions: Array<{
    toStatus: string
    label: string
    requiredAnyScopes: string[]
  }>
  allowedTransitionsByStatus: Record<string, string[]>
}

type ConnectorRegistryEntryView = {
  provider: ConnectorProvider
  displayName: string
  description?: string | null
  implementationPath?: string | null
  supportedAssetKinds: string[]
}

type ConnectorInstanceView = {
  id: string
  provider: ConnectorProvider
  displayName: string
  workspaceId?: string | null
  tenantId?: string | null
  configuration: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

type ConnectorFormState = {
  provider: ConnectorProvider
  workspaceId: string
  tenantId: string
  displayName: string
  parametersJson: string
  credentialDrafts: Array<{ name: string; secretStore: string; secretValue: string }>
  secretRefsJson: string
  baseUrl: string
  openapiUrl: string
  requestTimeoutSeconds: string
  apiOperationsJson: string
  accountUrl: string
  fileSystemsText: string
  pathPrefixesText: string
  deliveryLocationsText: string
}

const TAB_OPTIONS: Array<{ value: ConnectorTab; label: string }> = [
  { value: 'setup', label: 'Setup' },
  { value: 'validation', label: 'Validation' },
  { value: 'sync', label: 'Sync status' },
]

const CONNECTOR_STATUS_TONES: Record<string, 'neutral' | 'success' | 'info' | 'warning' | 'error'> = {
  queued: 'neutral',
  running: 'info',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
}

const INITIAL_FORM_STATE = (workspaceId = ''): ConnectorFormState => ({
  provider: 'external_api',
  workspaceId,
  tenantId: '',
  displayName: '',
  parametersJson: '{}',
  credentialDrafts: [{ name: '', secretStore: '', secretValue: '' }],
  secretRefsJson: '[]',
  baseUrl: '',
  openapiUrl: '',
  requestTimeoutSeconds: '30',
  apiOperationsJson: '[]',
  accountUrl: '',
  fileSystemsText: '',
  pathPrefixesText: '',
  deliveryLocationsText: '',
})

const trimToNull = (value: string): string | null => {
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

const parseJsonObject = (value: string, fieldName: string): Record<string, unknown> => {
  const trimmed = value.trim()
  if (!trimmed) {
    return {}
  }

  const parsed = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${fieldName} must be a JSON object.`)
  }

  return parsed as Record<string, unknown>
}

const parseJsonArray = (value: string, fieldName: string): unknown[] => {
  const trimmed = value.trim()
  if (!trimmed) {
    return []
  }

  const parsed = JSON.parse(trimmed)
  if (!Array.isArray(parsed)) {
    throw new Error(`${fieldName} must be a JSON array.`)
  }

  return parsed
}

const parseDelimitedList = (value: string): string[] =>
  value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)

const parsePositiveInteger = (value: string, fieldName: string): number | null => {
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }

  const parsed = Number.parseInt(trimmed, 10)
  if (!Number.isFinite(parsed) || parsed < 1) {
    throw new Error(`${fieldName} must be a positive integer.`)
  }

  return parsed
}

const formatDateTime = (value: string | null | undefined): string => {
  if (!value) {
    return 'Unavailable'
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}

const formatErrorMessage = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message
  }
  return String(error || 'Unknown error')
}

const normalizeSecretDraft = (draft: { name: string; secretStore: string; secretValue: string }) => ({
  name: draft.name.trim(),
  secretStore: draft.secretStore.trim(),
  secretValue: draft.secretValue,
})

const redactRequestSecrets = (payload: Record<string, unknown>): Record<string, unknown> => {
  const clone = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>
  if (Array.isArray(clone.credentials)) {
    clone.credentials = clone.credentials.map((credential) => {
      if (!credential || typeof credential !== 'object') {
        return credential
      }

      const credentialRecord = { ...(credential as Record<string, unknown>) }
      if (Object.prototype.hasOwnProperty.call(credentialRecord, 'value')) {
        credentialRecord.value = '[redacted]'
      }
      return credentialRecord
    })
  }

  return clone
}

const buildToneForStatus = (status: string): 'neutral' | 'success' | 'info' | 'warning' | 'error' => {
  return CONNECTOR_STATUS_TONES[status] || 'neutral'
}

const buildRequestConfiguration = (form: ConnectorFormState, connectorInstanceId?: string | null): Record<string, unknown> => {
  const configuration: Record<string, unknown> = {
    provider: form.provider,
  }

  const workspaceId = trimToNull(form.workspaceId)
  if (workspaceId) {
    configuration.workspaceId = workspaceId
  }

  const tenantId = trimToNull(form.tenantId)
  if (tenantId) {
    configuration.tenantId = tenantId
  }

  const displayName = trimToNull(form.displayName)
  if (displayName) {
    configuration.displayName = displayName
  }

  const credentials = form.credentialDrafts
    .map(normalizeSecretDraft)
    .filter((credential) => credential.name || credential.secretStore || credential.secretValue)
    .map((credential) => {
      if (!credential.name) {
        throw new Error('Each secret credential row requires a credential name.')
      }
      if (!credential.secretValue) {
        throw new Error(`Secret value is required for ${credential.name}.`)
      }

      return {
        name: credential.name,
        value: credential.secretValue,
        ...(credential.secretStore ? { secret_store: credential.secretStore } : {}),
      }
    })

  if (credentials.length > 0) {
    configuration.credentials = credentials
  }

  const parameters = parseJsonObject(form.parametersJson, 'Connection parameters')
  if (Object.keys(parameters).length > 0) {
    configuration.parameters = parameters
  }

  const secretRefs = parseJsonArray(form.secretRefsJson, 'Secret references')
  if (secretRefs.length > 0) {
    configuration.secretRefs = secretRefs
  }

  switch (form.provider) {
    case 'postgresql':
    case 'sql_server':
      break
    case 'external_api': {
      const baseUrl = trimToNull(form.baseUrl)
      if (!baseUrl) {
        throw new Error('Base URL is required for the External API connector.')
      }

      configuration.baseUrl = baseUrl

      const timeout = parsePositiveInteger(form.requestTimeoutSeconds, 'Request timeout seconds')
      if (timeout !== null) {
        configuration.requestTimeoutSeconds = timeout
      }

      const openapiUrl = trimToNull(form.openapiUrl)
      if (openapiUrl) {
        configuration.openapiUrl = openapiUrl
      }

      const apiOperations = parseJsonArray(form.apiOperationsJson, 'API operations')
      if (apiOperations.length > 0) {
        configuration.apiOperations = apiOperations
      }

      if (!openapiUrl && apiOperations.length === 0) {
        throw new Error('Provide either an OpenAPI URL or an API operations array for the External API connector.')
      }
      break
    }
    case 'azure_adls': {
      const accountUrl = trimToNull(form.accountUrl)
      if (!accountUrl) {
        throw new Error('Account URL is required for Azure ADLS.')
      }

      configuration.accountUrl = accountUrl

      const timeout = parsePositiveInteger(form.requestTimeoutSeconds, 'Request timeout seconds')
      if (timeout !== null) {
        configuration.requestTimeoutSeconds = timeout
      }

      const fileSystems = parseDelimitedList(form.fileSystemsText)
      if (fileSystems.length > 0) {
        configuration.fileSystems = fileSystems
      }

      const pathPrefixes = parseDelimitedList(form.pathPrefixesText)
      if (pathPrefixes.length > 0) {
        configuration.pathPrefixes = pathPrefixes
      }
      break
    }
    case 's3_blob': {
      const deliveryLocations = parseDelimitedList(form.deliveryLocationsText)
      if (deliveryLocations.length === 0) {
        throw new Error('At least one delivery location is required for S3 / Blob.')
      }

      configuration.deliveryLocations = deliveryLocations
      break
    }
  }

  const requestPayload: Record<string, unknown> = { configuration }
  if (connectorInstanceId) {
    requestPayload.connectorInstanceId = connectorInstanceId
  }
  return camelToSnake(requestPayload)
}

const getApiErrorMessage = async (response: Response, fallback: string): Promise<string> => {
  try {
    const payload = await response.json()
    if (typeof payload === 'string') {
      return payload
    }

    if (payload && typeof payload === 'object') {
      const detail = (payload as Record<string, unknown>).detail
      if (typeof detail === 'string') {
        return detail
      }
      if (detail && typeof detail === 'object') {
        const detailRecord = detail as Record<string, unknown>
        if (typeof detailRecord.message === 'string' && detailRecord.message.trim()) {
          return detailRecord.message
        }
        if (typeof detailRecord.error === 'string' && detailRecord.error.trim()) {
          return detailRecord.error
        }
        return JSON.stringify(detailRecord)
      }

      const message = (payload as Record<string, unknown>).message
      if (typeof message === 'string' && message.trim()) {
        return message
      }
    }
  } catch {
    // fall through to the generic error below
  }

  return fallback
}

export const ConnectorWorkbench: React.FC = () => {
  const auth = useAuth()
  const settings = useSettings()
  const [activeTab, setActiveTab] = useState<ConnectorTab>('setup')
  const [showAgentAssistant, setShowAgentAssistant] = useState(false)
  const [form, setForm] = useState<ConnectorFormState>(() => INITIAL_FORM_STATE(''))
  const [actionLoading, setActionLoading] = useState<'test' | 'discover' | 'sync' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [healthResult, setHealthResult] = useState<ConnectorHealthResultView | null>(null)
  const [discoveryResult, setDiscoveryResult] = useState<ConnectorDiscoveryResultView | null>(null)
  const [syncJob, setSyncJob] = useState<ConnectorSyncJobView | null>(null)
  const [statusModel, setStatusModel] = useState<ConnectorSyncStatusModelView | null>(null)
  const [statusModelLoading, setStatusModelLoading] = useState(true)
  const [statusModelError, setStatusModelError] = useState<string | null>(null)
  const [registryEntries, setRegistryEntries] = useState<ConnectorRegistryEntryView[]>([])
  const [registryLoading, setRegistryLoading] = useState(true)
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [connectorInstances, setConnectorInstances] = useState<ConnectorInstanceView[]>([])
  const [connectorInstancesLoading, setConnectorInstancesLoading] = useState(true)
  const [connectorInstancesError, setConnectorInstancesError] = useState<string | null>(null)
  const [instanceSaveLoading, setInstanceSaveLoading] = useState(false)
  const [instanceSaveError, setInstanceSaveError] = useState<string | null>(null)
  const [savedConnectorInstanceId, setSavedConnectorInstanceId] = useState<string | null>(null)

  const isAuthenticated = auth.isAuthenticated
  const hasAdminWorkspaceAccess = Boolean(
    isAuthenticated && auth.currentWorkspaceId && auth.user?.workspaceRoles.some((workspaceRole) => {
      return workspaceRole.workspaceId === auth.currentWorkspaceId && (workspaceRole.role === 'admin' || workspaceRole.role === 'cross-admin')
    }),
  )
  const apiBase = useMemo(() => {
    try {
      return toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
    } catch {
      return ''
    }
  }, [settings.applicationSettings?.apiBaseUrl])
  const providerOption = registryEntries.find((option) => option.provider === form.provider) || null
  const connectorAssistantPrompt = useMemo(() => {
    const providerLabel = providerOption?.displayName ?? 'this connector'
    return `Help me configure an ${providerLabel.toLowerCase()} connector for workspace ${form.workspaceId || 'the current workspace'}. Suggest the required fields, secret references, validation checks, and a safe sync plan based on the current setup.`
  }, [form.workspaceId, providerOption])

  useEffect(() => {
    if (auth.currentWorkspaceId && !form.workspaceId) {
      setForm((currentForm) => (
        currentForm.workspaceId ? currentForm : { ...currentForm, workspaceId: auth.currentWorkspaceId as string }
      ))
    }
  }, [auth.currentWorkspaceId, form.workspaceId])

  const loadConnectorRegistry = useCallback(async () => {
    setRegistryLoading(true)
    setRegistryError(null)

    try {
      if (!apiBase) {
        throw new Error('API base URL is not configured.')
      }

      const token = getAuthToken()
      const response = await fetch(`${apiBase}/connectors/registry`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })

      if (!response.ok) {
        throw new Error(await getApiErrorMessage(response, `Unable to load connector registry (${response.status}).`))
      }

      const payload = snakeToCamel<ConnectorRegistryEntryView[]>(await response.json())
      setRegistryEntries(payload)
    } catch (error) {
      setRegistryEntries([])
      setRegistryError(formatErrorMessage(error))
    } finally {
      setRegistryLoading(false)
    }
  }, [apiBase])

  const loadConnectorInstances = useCallback(async (provider: ConnectorProvider) => {
    setConnectorInstancesLoading(true)
    setConnectorInstancesError(null)

    try {
      if (!apiBase) {
        throw new Error('API base URL is not configured.')
      }

      const params = new URLSearchParams({ provider })
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/connectors/instances?${params.toString()}`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })

      if (!response.ok) {
        throw new Error(await getApiErrorMessage(response, `Unable to load connector instances (${response.status}).`))
      }

      const payload = snakeToCamel<ConnectorInstanceView[]>(await response.json())
      setConnectorInstances(payload)
    } catch (error) {
      setConnectorInstances([])
      setConnectorInstancesError(formatErrorMessage(error))
    } finally {
      setConnectorInstancesLoading(false)
    }
  }, [apiBase])

  const loadStatusModel = useCallback(async () => {
    setStatusModelLoading(true)
    setStatusModelError(null)

    try {
      if (!apiBase) {
        throw new Error('API base URL is not configured.')
      }

      const token = getAuthToken()
      const response = await fetch(`${apiBase}/governance/status-models/connector_sync_job`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })

      if (!response.ok) {
        throw new Error(await getApiErrorMessage(response, `Unable to load connector sync status model (${response.status}).`))
      }

      const payload = snakeToCamel<ConnectorSyncStatusModelView>(await response.json())
      setStatusModel(payload)
    } catch (error) {
      setStatusModel(null)
      setStatusModelError(formatErrorMessage(error))
    } finally {
      setStatusModelLoading(false)
    }
  }, [apiBase])

  useEffect(() => {
    if (!hasAdminWorkspaceAccess) {
      return
    }

    void loadConnectorRegistry()
    void loadStatusModel()
  }, [hasAdminWorkspaceAccess, loadConnectorRegistry, loadStatusModel])

  useEffect(() => {
    if (!hasAdminWorkspaceAccess || !form.provider) {
      return
    }

    void loadConnectorInstances(form.provider)
  }, [form.provider, hasAdminWorkspaceAccess, loadConnectorInstances])

  useEffect(() => {
    if (registryEntries.length === 0) {
      return
    }

    if (registryEntries.some((entry) => entry.provider === form.provider)) {
      return
    }

    setForm((currentForm) => {
      if (registryEntries.some((entry) => entry.provider === currentForm.provider)) {
        return currentForm
      }
      return { ...currentForm, provider: registryEntries[0].provider }
    })
  }, [form.provider, registryEntries])

  const saveConnectorInstance = useCallback(async () => {
    setInstanceSaveLoading(true)
    setInstanceSaveError(null)

    try {
      if (!apiBase) {
        throw new Error('API base URL is not configured.')
      }

      const requestBody = buildRequestConfiguration(form, savedConnectorInstanceId)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/connectors/instances`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        throw new Error(await getApiErrorMessage(response, `Connector instance save failed (${response.status}).`))
      }

      const payload = snakeToCamel<ConnectorInstanceView>(await response.json())
      setSavedConnectorInstanceId(payload.id)
      await loadConnectorInstances(form.provider)
    } catch (error) {
      setInstanceSaveError(formatErrorMessage(error))
    } finally {
      setInstanceSaveLoading(false)
    }
  }, [apiBase, form, loadConnectorInstances, savedConnectorInstanceId])

  const resetWorkbench = useCallback(() => {
    setForm(INITIAL_FORM_STATE(auth.currentWorkspaceId || ''))
    setActionError(null)
    setHealthResult(null)
    setDiscoveryResult(null)
    setSyncJob(null)
    setActiveTab('setup')
  }, [auth.currentWorkspaceId])

  const runConnectorAction = useCallback(async (action: 'test' | 'discover' | 'sync') => {
    setActionLoading(action)
    setActionError(null)

    try {
      if (!apiBase) {
        throw new Error('API base URL is not configured.')
      }

      const requestBody = buildRequestConfiguration(form, savedConnectorInstanceId)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/connectors/${encodeURIComponent(form.provider)}/${action === 'test' ? 'test-connection' : action === 'discover' ? 'discover-assets' : 'sync'}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        throw new Error(await getApiErrorMessage(response, `Connector ${action} request failed (${response.status}).`))
      }

      if (action === 'test') {
        setHealthResult(snakeToCamel<ConnectorHealthResultView>(await response.json()))
        setActiveTab('validation')
        return
      }

      if (action === 'discover') {
        setDiscoveryResult(snakeToCamel<ConnectorDiscoveryResultView>(await response.json()))
        setActiveTab('validation')
        return
      }

      setSyncJob(snakeToCamel<ConnectorSyncJobView>(await response.json()))
      setActiveTab('sync')
    } catch (error) {
      setActionError(formatErrorMessage(error))
    } finally {
      setActionLoading(null)
    }
  }, [apiBase, form, savedConnectorInstanceId])

  const requestPreview = useMemo(() => {
    try {
      const payload = buildRequestConfiguration(form, savedConnectorInstanceId)
      return {
        payload: redactRequestSecrets(payload),
        error: null as string | null,
      }
    } catch (error) {
      return {
        payload: null,
        error: formatErrorMessage(error),
      }
    }
  }, [form, savedConnectorInstanceId])

  if (!isAuthenticated) {
    return (
      <AppPageShell className="connector-workbench connector-workbench--locked">
        <AppEmptyState
          title="Sign in to configure connectors"
          description="Connector setup and sync tools are available to authenticated administrators."
        />
      </AppPageShell>
    )
  }

  if (!hasAdminWorkspaceAccess) {
    return (
      <AppPageShell className="connector-workbench connector-workbench--locked">
        <AppEmptyState
          title="Access restricted"
          description="Connector setup and sync tools are available to administrators only."
        />
      </AppPageShell>
    )
  }

  return (
    <AppPageShell className="connector-workbench">
      <AppPageHeader
        className="connector-workbench__header"
        eyebrow="Connector onboarding"
        title="Connector workbench"
        description="Configure provider-specific connector details, validate access, discover assets, and run metadata syncs from a single backend-owned flow."
        actions={(
          <div className="connector-workbench__header-actions">
            <SecondaryButton onClick={() => setShowAgentAssistant((current) => !current)}>
              {showAgentAssistant ? 'Hide AI assistant' : 'Use AI assistant'}
            </SecondaryButton>
            <SecondaryButton onClick={() => void saveConnectorInstance()} disabled={actionLoading !== null || instanceSaveLoading}>
              {instanceSaveLoading ? 'Saving…' : 'Save instance'}
            </SecondaryButton>
            <PrimaryButton onClick={() => void runConnectorAction('test')} disabled={actionLoading !== null}>
              {actionLoading === 'test' ? 'Testing…' : 'Test connection'}
            </PrimaryButton>
            <SecondaryButton onClick={() => void runConnectorAction('discover')} disabled={actionLoading !== null}>
              {actionLoading === 'discover' ? 'Discovering…' : 'Discover assets'}
            </SecondaryButton>
            <SecondaryButton onClick={() => void runConnectorAction('sync')} disabled={actionLoading !== null}>
              {actionLoading === 'sync' ? 'Syncing…' : 'Run sync'}
            </SecondaryButton>
            <TertiaryButton onClick={resetWorkbench} disabled={actionLoading !== null}>
              Reset form
            </TertiaryButton>
          </div>
        )}
      >
        <div className="connector-workbench__hero-stats">
          <div className="connector-workbench__hero-stat">
            <span>Selected provider</span>
            <strong>{providerOption?.displayName ?? 'Connector registry'}</strong>
            <p>{providerOption?.description ?? 'Loading persisted connector registry.'}</p>
          </div>
          <div className="connector-workbench__hero-stat">
            <span>Workspace scope</span>
            <strong>{form.workspaceId || 'Not selected'}</strong>
            <p>Saved with the connector payload if you provide one.</p>
          </div>
          <div className="connector-workbench__hero-stat">
            <span>Sync lifecycle model</span>
            <strong>{statusModel?.entity || (statusModelLoading ? 'Loading…' : 'Unavailable')}</strong>
            <p>{statusModelError || 'Backend-owned lifecycle states for connector sync jobs.'}</p>
          </div>
        </div>
      </AppPageHeader>

      {showAgentAssistant && (
        <AppPanel
          className="connector-workbench__panel connector-workbench__panel--assistant"
          title="Connector onboarding assistant"
          description="Use the existing dq-llm agent harness to get connector-specific guidance before you validate or sync the current setup."
        >
          <AgentChatPanel
            defaultAgentType="connector_onboarding"
            defaultPrompt={connectorAssistantPrompt}
            title="Connector onboarding assistant"
            description="Ask the agent for connector-specific setup guidance, secret recommendations, and validation steps for the current provider configuration."
          />
        </AppPanel>
      )}


      {actionError && (
        <AppPanel
          tone="muted"
          className="connector-workbench__notice connector-workbench__notice--error"
          title="Action failed"
          description={actionError}
        />
      )}

      {registryError && (
        <AppPanel
          tone="muted"
          className="connector-workbench__notice"
          title="Connector registry unavailable"
          description={registryError}
        />
      )}

      {instanceSaveError && (
        <AppPanel
          tone="muted"
          className="connector-workbench__notice connector-workbench__notice--error"
          title="Connector instance save failed"
          description={instanceSaveError}
        />
      )}

      {connectorInstancesError && (
        <AppPanel
          tone="muted"
          className="connector-workbench__notice"
          title="Connector instances unavailable"
          description={connectorInstancesError}
        />
      )}

      {statusModelError && (
        <AppPanel
          tone="muted"
          className="connector-workbench__notice"
          title="Sync lifecycle unavailable"
          description={statusModelError}
        />
      )}

      <div className="connector-workbench__layout">
        <main className="connector-workbench__main">
          <AppTabs
            ariaLabel="Connector workbench sections"
            value={activeTab}
            onChange={setActiveTab}
            tabs={TAB_OPTIONS}
            className="connector-workbench__tabs"
          />

          <AppPanel
            className="connector-workbench__panel connector-workbench__panel--setup"
            title="Connector setup"
            description={providerOption?.description ?? 'Loading persisted connector registry.'}
          >
            <div className="connector-workbench__form-grid">
              <AppSelect
                id="connector-provider"
                label="Provider"
                value={form.provider}
                onChange={(value) => {
                  const provider = value as ConnectorProvider
                  setForm((currentForm) => ({ ...currentForm, provider }))
                  setSavedConnectorInstanceId(null)
                  setActionError(null)
                  setHealthResult(null)
                  setDiscoveryResult(null)
                  setSyncJob(null)
                }}
                options={registryEntries.map((option) => ({ value: option.provider, label: option.displayName }))}
                hint={registryLoading ? 'Loading the persisted connector registry.' : 'Choose the backend connector family to configure.'}
                disabled={registryLoading || registryEntries.length === 0}
              />

              <AppInput
                id="connector-workspace-id"
                label="Workspace ID"
                value={form.workspaceId}
                onChange={(event) => setForm((currentForm) => ({ ...currentForm, workspaceId: event.target.value }))}
                placeholder="workspace-1"
                hint="Optional, but useful when the connector should be scoped to a workspace."
              />

              <AppInput
                id="connector-tenant-id"
                label="Tenant ID"
                value={form.tenantId}
                onChange={(event) => setForm((currentForm) => ({ ...currentForm, tenantId: event.target.value }))}
                placeholder="tenant-1"
                hint="Optional multi-tenant scoping value."
              />

              <AppInput
                id="connector-display-name"
                label="Display name"
                value={form.displayName}
                onChange={(event) => setForm((currentForm) => ({ ...currentForm, displayName: event.target.value }))}
                placeholder="Retail Orders API"
                hint="A friendly label for this connector setup."
              />
            </div>

            <div className="connector-workbench__field-group">
              <h3>Common configuration</h3>
              <div className="connector-workbench__form-grid connector-workbench__form-grid--stacked">
                <AppTextarea
                  id="connector-parameters-json"
                  label="Connection parameters JSON"
                  value={form.parametersJson}
                  onChange={(event) => setForm((currentForm) => ({ ...currentForm, parametersJson: event.target.value }))}
                  placeholder={`{
  "host": "db.example.com",
  "database": "catalog"
}`}
                  hint="Use backend field names such as host, database, username, driver, sslmode, or any provider-specific parameters."
                />

                <AppTextarea
                  id="connector-secret-refs-json"
                  label="Secret references JSON"
                  value={form.secretRefsJson}
                  onChange={(event) => setForm((currentForm) => ({ ...currentForm, secretRefsJson: event.target.value }))}
                  placeholder={`[
  {
    "name": "password_ref",
    "secret_ref": "vault://connectors/example/password"
  }
]`}
                  hint="Use secret references when the connector should resolve credentials from a secret store."
                />
              </div>
            </div>

            <div className="connector-workbench__field-group">
              <div className="connector-workbench__field-row-header">
                <h3>Secrets</h3>
                <TertiaryButton
                  onClick={() => setForm((currentForm) => ({
                    ...currentForm,
                    credentialDrafts: [...currentForm.credentialDrafts, { name: '', secretStore: '', secretValue: '' }],
                  }))}
                >
                  Add secret
                </TertiaryButton>
              </div>
              <p className="connector-workbench__muted-text">
                Secret values are write-only. Existing values are never shown; enter a new value to rotate a secret.
              </p>
              <div className="connector-workbench__secret-list">
                {form.credentialDrafts.map((credentialDraft, index) => (
                  <div key={`credential-${index}`} className="connector-workbench__secret-card">
                    <AppInput
                      id={`connector-credential-name-${index}`}
                      label="Credential name"
                      value={credentialDraft.name}
                      onChange={(event) => setForm((currentForm) => ({
                        ...currentForm,
                        credentialDrafts: currentForm.credentialDrafts.map((draft, draftIndex) => (
                          draftIndex === index ? { ...draft, name: event.target.value } : draft
                        )),
                      }))}
                      placeholder="password"
                      hint="The canonical secret name used by the connector configuration."
                    />
                    <AppInput
                      id={`connector-credential-secret-store-${index}`}
                      label="Secret store"
                      value={credentialDraft.secretStore}
                      onChange={(event) => setForm((currentForm) => ({
                        ...currentForm,
                        credentialDrafts: currentForm.credentialDrafts.map((draft, draftIndex) => (
                          draftIndex === index ? { ...draft, secretStore: event.target.value } : draft
                        )),
                      }))}
                      placeholder="vault"
                      hint="Optional store label used for secret resolution."
                    />
                    <AppInput
                      id={`connector-credential-secret-value-${index}`}
                      label="Secret value"
                      type="password"
                      value={credentialDraft.secretValue}
                      onChange={(event) => setForm((currentForm) => ({
                        ...currentForm,
                        credentialDrafts: currentForm.credentialDrafts.map((draft, draftIndex) => (
                          draftIndex === index ? { ...draft, secretValue: event.target.value } : draft
                        )),
                      }))}
                      placeholder="••••••••"
                      hint="Write-only. The value is never shown back once entered."
                    />
                    <div className="connector-workbench__secret-actions">
                      <TertiaryButton
                        onClick={() => setForm((currentForm) => ({
                          ...currentForm,
                          credentialDrafts: currentForm.credentialDrafts.filter((_, draftIndex) => draftIndex !== index),
                        }))}
                        disabled={form.credentialDrafts.length === 1}
                      >
                        Remove secret
                      </TertiaryButton>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {form.provider === 'external_api' && (
              <div className="connector-workbench__field-group">
                <h3>External API settings</h3>
                <div className="connector-workbench__form-grid">
                  <AppInput
                    id="connector-base-url"
                    label="Base URL"
                    value={form.baseUrl}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, baseUrl: event.target.value }))}
                    placeholder="https://api.example.com"
                    required
                    hint="Required for the external API connector."
                  />

                  <AppInput
                    id="connector-openapi-url"
                    label="OpenAPI URL"
                    value={form.openapiUrl}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, openapiUrl: event.target.value }))}
                    placeholder="https://api.example.com/openapi.json"
                    hint="Optional when you are supplying explicit API operations instead."
                  />

                  <AppInput
                    id="connector-request-timeout"
                    label="Request timeout seconds"
                    value={form.requestTimeoutSeconds}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, requestTimeoutSeconds: event.target.value }))}
                    placeholder="30"
                    hint="Positive integer timeout used for connector requests."
                  />

                  <AppTextarea
                    id="connector-api-operations-json"
                    label="API operations JSON"
                    value={form.apiOperationsJson}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, apiOperationsJson: event.target.value }))}
                    placeholder={`[
  {
    "name": "list_customers",
    "method": "GET",
    "path": "/customers"
  }
]`}
                    hint="Optional when the backend should use explicitly declared API operations."
                  />
                </div>
              </div>
            )}

            {form.provider === 'azure_adls' && (
              <div className="connector-workbench__field-group">
                <h3>Azure ADLS settings</h3>
                <div className="connector-workbench__form-grid">
                  <AppInput
                    id="connector-account-url"
                    label="Account URL"
                    value={form.accountUrl}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, accountUrl: event.target.value }))}
                    placeholder="https://account.dfs.core.windows.net"
                    required
                    hint="Required for Azure ADLS discovery."
                  />

                  <AppInput
                    id="connector-request-timeout-adls"
                    label="Request timeout seconds"
                    value={form.requestTimeoutSeconds}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, requestTimeoutSeconds: event.target.value }))}
                    placeholder="30"
                    hint="Positive integer timeout used for connector requests."
                  />

                  <AppTextarea
                    id="connector-file-systems"
                    label="File systems"
                    value={form.fileSystemsText}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, fileSystemsText: event.target.value }))}
                    placeholder="warehouse, curated"
                    hint="Comma or newline separated file system names."
                  />

                  <AppTextarea
                    id="connector-path-prefixes"
                    label="Path prefixes"
                    value={form.pathPrefixesText}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, pathPrefixesText: event.target.value }))}
                    placeholder="raw, landing"
                    hint="Comma or newline separated prefixes to scan."
                  />
                </div>
              </div>
            )}

            {form.provider === 's3_blob' && (
              <div className="connector-workbench__field-group">
                <h3>S3 / Blob settings</h3>
                <div className="connector-workbench__form-grid">
                  <AppTextarea
                    id="connector-delivery-locations"
                    label="Delivery locations"
                    value={form.deliveryLocationsText}
                    onChange={(event) => setForm((currentForm) => ({ ...currentForm, deliveryLocationsText: event.target.value }))}
                    placeholder={`s3://dq-test-data/landing
s3a://archive-bucket/exports`}
                    required
                    hint="Comma or newline separated delivery locations to ingest."
                  />
                </div>
              </div>
            )}

            <div className="connector-workbench__field-group">
              <h3>Provider notes</h3>
              <p className="connector-workbench__muted-text">{providerOption?.description ?? 'Loading persisted connector registry.'}</p>
            </div>
          </AppPanel>

          <AppPanel
            className="connector-workbench__panel connector-workbench__panel--instances"
            title="Persisted instances"
            description="Stored connector instances for the selected provider are loaded from the backend repository."
            actions={(
              <SecondaryButton onClick={() => void loadConnectorInstances(form.provider)} disabled={connectorInstancesLoading}>
                {connectorInstancesLoading ? 'Refreshing…' : 'Refresh'}
              </SecondaryButton>
            )}
          >
            {connectorInstances.length > 0 ? (
              <div className="connector-workbench__instance-list">
                {connectorInstances.map((instance) => (
                  <article key={instance.id} className="connector-workbench__instance-card">
                    <div className="connector-workbench__result-header">
                      <AppBadge tone="info">{instance.provider}</AppBadge>
                      <span>{instance.displayName}</span>
                    </div>
                    <dl className="connector-workbench__result-grid">
                      <div>
                        <dt>Instance ID</dt>
                        <dd>{instance.id}</dd>
                      </div>
                      <div>
                        <dt>Workspace</dt>
                        <dd>{instance.workspaceId || 'Not set'}</dd>
                      </div>
                      <div>
                        <dt>Tenant</dt>
                        <dd>{instance.tenantId || 'Not set'}</dd>
                      </div>
                      <div>
                        <dt>Created</dt>
                        <dd>{formatDateTime(instance.createdAt)}</dd>
                      </div>
                      <div>
                        <dt>Updated</dt>
                        <dd>{formatDateTime(instance.updatedAt)}</dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            ) : (
              <AppEmptyState
                title="No persisted connector instances yet"
                description="Save the current connector setup to create the first persisted instance for this provider."
              />
            )}
          </AppPanel>

          {activeTab === 'validation' && (
            <div className="connector-workbench__result-stack">
              <AppPanel
                className="connector-workbench__panel"
                title="Connection test"
                description="Runs the backend-owned validation flow and returns connector health details."
              >
                {healthResult ? (
                  <div className="connector-workbench__result-card">
                    <div className="connector-workbench__result-header">
                      <AppBadge tone={buildToneForStatus(healthResult.status)}>{healthResult.status}</AppBadge>
                      <span>Provider: {healthResult.provider}</span>
                    </div>
                    <dl className="connector-workbench__result-grid">
                      <div>
                        <dt>Operation count</dt>
                        <dd>{typeof healthResult.details.operationCount === 'number' ? healthResult.details.operationCount : 'Unavailable'}</dd>
                      </div>
                      <div>
                        <dt>Correlation</dt>
                        <dd>{typeof healthResult.details.correlationId === 'string' ? String(healthResult.details.correlationId) : 'Unavailable'}</dd>
                      </div>
                    </dl>
                    {healthResult.errors.length > 0 && (
                      <div className="connector-workbench__error-box">
                        <strong>Validation issues</strong>
                        <ul>
                          {healthResult.errors.map((error, index) => (
                            <li key={`${error.kind}-${index}`}>
                              {error.code ? `${error.code}: ` : ''}{error.message}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : (
                  <AppEmptyState
                    title="No connection test yet"
                    description="Run the connection test to see backend validation and health details."
                  />
                )}
              </AppPanel>

              <AppPanel
                className="connector-workbench__panel"
                title="Asset discovery"
                description="Discovers assets the connector exposes to the catalog."
              >
                {discoveryResult ? (
                  <div className="connector-workbench__result-card">
                    <div className="connector-workbench__result-header">
                      <AppBadge tone="info">{discoveryResult.items.length} item{discoveryResult.items.length === 1 ? '' : 's'}</AppBadge>
                      <span>Provider: {discoveryResult.provider}</span>
                    </div>
                    {discoveryResult.errors.length > 0 && (
                      <div className="connector-workbench__error-box">
                        <strong>Discovery issues</strong>
                        <ul>
                          {discoveryResult.errors.map((error, index) => (
                            <li key={`${error.kind}-${index}`}>
                              {error.code ? `${error.code}: ` : ''}{error.message}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <ul className="connector-workbench__item-list">
                      {discoveryResult.items.map((item) => (
                        <li key={item.identifier}>
                          <strong>{item.name || item.identifier}</strong>
                          <span>{item.kind}</span>
                          <code>{item.identifier}</code>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <AppEmptyState
                    title="No discovery yet"
                    description="Run discovery to see the catalog assets the connector exposes."
                  />
                )}
              </AppPanel>
            </div>
          )}

          {activeTab === 'sync' && (
            <AppPanel
              className="connector-workbench__panel"
              title="Sync job result"
              description="Metadata sync runs through the backend and returns a completed job record immediately."
            >
              {syncJob ? (
                <div className="connector-workbench__result-card">
                  <div className="connector-workbench__result-header">
                    <AppBadge tone={buildToneForStatus(syncJob.status)}>{syncJob.status}</AppBadge>
                    <span>Job {syncJob.jobId}</span>
                  </div>

                  <dl className="connector-workbench__result-grid connector-workbench__result-grid--sync">
                    <div>
                      <dt>Synced count</dt>
                      <dd>{syncJob.syncedCount}</dd>
                    </div>
                    <div>
                      <dt>Correlation ID</dt>
                      <dd>{syncJob.correlationId}</dd>
                    </div>
                    <div>
                      <dt>Requested at</dt>
                      <dd>{formatDateTime(syncJob.requestedAt)}</dd>
                    </div>
                    <div>
                      <dt>Completed at</dt>
                      <dd>{formatDateTime(syncJob.completedAt)}</dd>
                    </div>
                  </dl>

                  <div className="connector-workbench__result-panel">
                    <strong>Sync result</strong>
                    <p>
                      {syncJob.result.provider} synchronized {syncJob.result.syncedCount} item{syncJob.result.syncedCount === 1 ? '' : 's'}.
                    </p>
                  </div>

                  {syncJob.result.errors.length > 0 && (
                    <div className="connector-workbench__error-box">
                      <strong>Sync issues</strong>
                      <ul>
                        {syncJob.result.errors.map((error, index) => (
                          <li key={`${error.kind}-${index}`}>
                            {error.code ? `${error.code}: ` : ''}{error.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <ul className="connector-workbench__item-list connector-workbench__item-list--compact">
                    {syncJob.result.items.map((item) => (
                      <li key={item.identifier}>
                        <strong>{item.name || item.identifier}</strong>
                        <span>{item.kind}</span>
                        <code>{item.identifier}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <AppEmptyState
                  title="No sync job yet"
                  description="Run sync to create a connector sync job and inspect the completed result."
                />
              )}
            </AppPanel>
          )}
        </main>

        <aside className="connector-workbench__rail">
          <AppPanel
            className="connector-workbench__panel connector-workbench__panel--rail"
            title="Sync lifecycle"
            description="These states come from the backend status model and should stay canonical across the UI."
          >
            {statusModelLoading ? (
              <p className="connector-workbench__muted-text">Loading sync lifecycle model…</p>
            ) : statusModel ? (
              <div className="connector-workbench__rail-stack">
                <div className="connector-workbench__status-list">
                  {statusModel.statuses.map((status) => (
                    <div key={status.value} className="connector-workbench__status-item">
                      <AppBadge tone={status.isTerminal ? (status.value === 'completed' ? 'success' : 'warning') : status.isInitial ? 'info' : 'neutral'}>
                        {status.label}
                      </AppBadge>
                      <p>{status.description || 'No description provided.'}</p>
                    </div>
                  ))}
                </div>

                <div>
                  <strong>Transitions from current sync status</strong>
                  <ul className="connector-workbench__transition-list">
                    {(statusModel.allowedTransitionsByStatus[syncJob?.status || 'queued'] || statusModel.allowedTransitionsByStatus.queued || []).map((transition) => (
                      <li key={transition}>{transition}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <AppEmptyState
                title="Lifecycle unavailable"
                description="The backend status model could not be loaded. Sync actions still work, but the status rail is incomplete."
              />
            )}
          </AppPanel>

          <AppPanel
            className="connector-workbench__panel connector-workbench__panel--rail"
            title="Prepared payload"
            description="This is the exact request body that will be sent to the connector endpoints."
          >
            {requestPreview.error ? (
              <div className="connector-workbench__error-box">
                <strong>Payload error</strong>
                <p>{requestPreview.error}</p>
              </div>
            ) : (
              <pre className="connector-workbench__json-preview">{JSON.stringify(requestPreview.payload, null, 2)}</pre>
            )}
          </AppPanel>
        </aside>
      </div>
    </AppPageShell>
  )
}
