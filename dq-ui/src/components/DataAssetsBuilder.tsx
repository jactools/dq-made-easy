import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import * as XLSX from 'xlsx'

import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { useDataProduct } from '../contexts/DataProductContext'
import { useSettings } from '../hooks/useContexts'
import { useAuth } from '../hooks/useKeycloak'
import type { DataAttribute, DataObject, DataObjectVersion, DataProduct, DataSet, DefinitionMappingTarget } from '../types/dataProducts'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { AdminPageHeader } from './AdminPageHeader'
import { AgentChatPanel } from './AgentChatPanel'
import { PrimaryButton, SecondaryButton, TertiaryButton } from './Button'
import { DiscussionPanel, normalizeDiscussionEntries } from './discussion/DiscussionPanel'
import './DataAssetsBuilder.css'

type DataAssetSummary = {
  id: string
  name: string
  description: string
  workspaceId: string
  status: string
  createdAt: string
  currentVersionId: string | null
  sourceObjectVersionIds: string[]
  businessContext: DataAssetBusinessContext | null
  dataContractDownloadUrl: string
}

type DataAssetBusinessContext = {
  datasetId: string
  dataProductId: string
  domain: string
  owner: string
  purpose: string
  steward: string
  criticality: string
  tags: string[]
  businessDefinitions: string[]
  lineageReferences: string[]
  consumers: string[]
}

type DataAssetLineageNode = {
  kind: string
  id: string
  name: string
  workspaceId: string | null
  detail: string | null
  navigationTarget: string | null
}

type DataAssetLineageImpactSummary = {
  contractChangeCount: number
  impactedRuleIds: string[]
  impactedMonitorScopeIds: string[]
  impactedIncidentIds: string[]
  notes: string[]
}

type DataAssetLineageBusinessContextOverlay = {
  domain: string
  purpose: string
  steward: string
  criticality: string
  consumers: string[]
  summary: string
}

type DataAssetLineageClassificationView = {
  classification: string
  rationale: string
  signals: string[]
}

type DataAssetLineageAnomalyAnnotation = {
  kind: string
  severity: string
  summary: string
  source: string
  details: Record<string, unknown>
}

type DataAssetGovernanceDiscovery = {
  assetId: string
  priority: string
  summary: string
  objectStorageClassifications: string[]
  evidenceClassifications: string[]
  signals: string[]
  latestDeliveryId: string | null
  latestDeliveryAt: string | null
  snapshotId: string | null
  capturedAt: string | null
}

type DataAssetLineage = {
  dataAsset: DataAssetSummary
  upstreamNodes: DataAssetLineageNode[]
  downstreamNodes: DataAssetLineageNode[]
  impactSummary: DataAssetLineageImpactSummary
  businessContextOverlay: DataAssetLineageBusinessContextOverlay | null
  classificationView: DataAssetLineageClassificationView | null
  anomalyAnnotations: DataAssetLineageAnomalyAnnotation[]
  snapshotId: string | null
  capturedAt: string | null
}

type DataAssetSourceBinding = {
  sourceDataObjectVersionId: string
  sourceFieldId: string
  sourceFieldName: string
  sourceFieldType: string
  nullable: boolean
  schemaLocked?: boolean
}

type DataAssetFilter = {
  expression: string
  enabled: boolean
  description: string | null
}

type DataAssetDerivedField = {
  name: string
  expression: string
  dataType: string | null
  nullable: boolean | null
  sourceFieldIds: string[]
}

type DataAssetUploadPreviewColumn = {
  name: string
  dataType: string
  nullable: boolean
}

type DataAssetUploadPreview = {
  fileName: string | null
  fileFormat: string | null
  sourceUri: string | null
  columns: DataAssetUploadPreviewColumn[]
}

type DataAssetVersion = {
  id: string
  dataAssetId: string
  version: number
  createdAt: string
  sourceBindings: DataAssetSourceBinding[]
  filters: DataAssetFilter[]
  derivedFields: DataAssetDerivedField[]
  uploadPreview: DataAssetUploadPreview | null
  dataContractDownloadUrl: string
}

type DataAssetValidation = {
  ok: boolean
  asset: DataAssetSummary
  version: DataAssetVersion
  issues: string[]
}

type DataAssetContractChange = {
  fieldName: string
  changeType: string
  severity: string
  message: string
}

type DataAssetContractComparison = {
  previousVersion: string
  currentVersion: string
  changeClassification: string
  summary: {
    breakingChanges: number
    compatibleChanges: number
    additiveChanges: number
    totalChanges: number
  }
  changes: DataAssetContractChange[]
}

type DataAssetContractIssue = {
  fieldName: string
  issueType: string
  severity: string
  message: string
}

type DataAssetContractConformance = {
  ok: boolean
  summary: {
    breakingIssues: number
    warningIssues: number
    totalIssues: number
  }
  issues: DataAssetContractIssue[]
}

type DataAssetContractVersion = {
  id?: string | null
  reviewStatus?: string | null
  reviewedBy?: string | null
  reviewedAt?: string | null
  reviewComments?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

type DataAssetContractAnalysis = {
  success: boolean
  dataAssetId: string
  contract: {
    version: string
    name: string
    status: string
    schema: {
      name: string
      fields: Array<Record<string, unknown>>
    }
  }
  comparison: DataAssetContractComparison | null
  conformance: DataAssetContractConformance
  latestContractVersion: DataAssetContractVersion | null
}

type AssetFormState = {
  id: string
  name: string
  description: string
  workspaceId: string
  status: string
  currentVersionId: string
  sourceObjectVersionIdsText: string
  businessContextDatasetId: string
  businessContextDataProductId: string
  businessContextDomain: string
  businessContextOwner: string
  businessContextPurpose: string
  businessContextSteward: string
  businessContextCriticality: string
  businessContextTagsText: string
  businessContextBusinessDefinitionsText: string
  businessContextLineageReferencesText: string
  businessContextConsumersText: string
}

type VersionFormState = {
  id: string
  version: string
  createdAt: string
  sourceBindings: DataAssetSourceBinding[]
  filters: DataAssetFilter[]
  derivedFields: DataAssetDerivedField[]
  uploadPreview: DataAssetUploadPreview
}

type ApiError = Error & { detail?: unknown }

export type DataAssetProtectionStatus = 'masked' | 'encrypted' | 'unprotected' | 'unavailable'

export type DataAssetProtectionReviewRow = {
  key: string
  attributeId: string
  attributeName: string
  sourceFieldType: string
  sourceDataObjectVersionId: string
  assetClassification: string
  assetPriority: string
  signals: string[]
  maskingMethod: string
  encryptionRequired: boolean
  encryptionKeyId: string
  status: DataAssetProtectionStatus
  statusDescription: string
  recommendation: string
  needsProtection: boolean
  target: DefinitionMappingTarget | null
}

export type DataAssetProtectionSummary = {
  advice: string
  sensitiveCount: number
  protectedCount: number
  unprotectedCount: number
  unavailableCount: number
}

const SENSITIVE_CLASSIFICATIONS = new Set(['confidential', 'high_value', 'restricted', 'sensitive'])
const SENSITIVE_PRIORITIES = new Set(['high', 'critical'])

const normalizeProtectionLabel = (value: unknown): string => String(value ?? '').trim().toLowerCase()

const getProtectionStatus = (attribute: DataAttribute | null | undefined): Pick<DataAssetProtectionReviewRow, 'status' | 'statusDescription' | 'maskingMethod' | 'encryptionRequired' | 'encryptionKeyId'> => {
  if (!attribute) {
    return {
      status: 'unavailable',
      statusDescription: 'Source attribute details could not be loaded',
      maskingMethod: '',
      encryptionRequired: false,
      encryptionKeyId: '',
    }
  }

  const maskingMethod = String(attribute.maskingMethod || '').trim()
  const encryptionRequired = attribute.encryptionRequired === true
  const encryptionKeyId = String(attribute.encryptionKeyId || '').trim()

  if (maskingMethod && maskingMethod !== 'none') {
    return {
      status: 'masked',
      statusDescription: `Masked via ${maskingMethod}`,
      maskingMethod,
      encryptionRequired,
      encryptionKeyId,
    }
  }

  if (encryptionRequired && encryptionKeyId) {
    return {
      status: 'encrypted',
      statusDescription: `Encrypted with key ${encryptionKeyId}`,
      maskingMethod,
      encryptionRequired,
      encryptionKeyId,
    }
  }

  if (encryptionRequired) {
    return {
      status: 'unprotected',
      statusDescription: 'Encryption is required, but no key is selected',
      maskingMethod,
      encryptionRequired,
      encryptionKeyId,
    }
  }

  return {
    status: 'unprotected',
    statusDescription: 'No masking or encryption is configured',
    maskingMethod,
    encryptionRequired,
    encryptionKeyId,
  }
}

const findDefinitionMappingTarget = (
  versionId: string,
  attributeId: string,
  products: DataProduct[],
  standaloneDatasets: DataSet[],
): DefinitionMappingTarget | null => {
  const locateVersion = (dataObjects: DataObject[]): { objectId: string } | null => {
    for (const dataObject of dataObjects) {
      const version = dataObject.versions?.find((candidate) => candidate.id === versionId)
      if (version) {
        return {
          objectId: dataObject.id,
        }
      }
    }

    return null
  }

  for (const product of products) {
    for (const dataset of product.datasets || []) {
      const location = locateVersion(dataset.dataObjects || [])
      if (location) {
        return {
          productId: product.id,
          datasetId: dataset.id,
          objectId: location.objectId,
          versionId,
          attributeId,
        }
      }
    }
  }

  for (const dataset of standaloneDatasets) {
    const location = locateVersion(dataset.dataObjects || [])
    if (location) {
      return {
        datasetId: dataset.id,
        objectId: location.objectId,
        versionId,
        attributeId,
      }
    }
  }

  return null
}

export const buildProtectionReviewRows = (
  selectedVersion: DataAssetVersion | null,
  sourceAttributesByVersionId: Record<string, DataAttribute[] | null>,
  classification: string,
  priority: string,
  products: DataProduct[],
  standaloneDatasets: DataSet[],
): DataAssetProtectionReviewRow[] => {
  if (!selectedVersion) {
    return []
  }

  const normalizedClassification = normalizeProtectionLabel(classification)
  const normalizedPriority = normalizeProtectionLabel(priority)
  const assetSignals: string[] = [
    normalizedClassification ? `classification:${normalizedClassification}` : '',
    normalizedPriority ? `priority:${normalizedPriority}` : '',
  ].filter(Boolean)

  return selectedVersion.sourceBindings.map((binding) => {
    const sourceAttributes = sourceAttributesByVersionId[binding.sourceDataObjectVersionId]
    const attribute = sourceAttributes?.find((candidate) => candidate.id === binding.sourceFieldId) || null
    const protection = getProtectionStatus(attribute)
    const classificationSignals = [
      normalizedClassification,
      attribute?.isCde ? 'cde' : '',
      attribute?.isPrimaryKey ? 'primary-key' : '',
      (attribute?.ruleCount || 0) > 0 ? 'rule-linked' : '',
    ].filter(Boolean)
    const needsProtection = Boolean(normalizedClassification && SENSITIVE_CLASSIFICATIONS.has(normalizedClassification))
      || Boolean(normalizedPriority && SENSITIVE_PRIORITIES.has(normalizedPriority))
      || Boolean(attribute?.isCde || attribute?.isPrimaryKey || (attribute?.ruleCount || 0) > 0)
    const recommendation = protection.status === 'unavailable'
      ? 'Source attribute details are unavailable in the catalog browser.'
      : needsProtection && protection.status === 'unprotected'
        ? 'Protect through masking or encryption.'
        : protection.status === 'masked'
          ? 'Masking is configured.'
          : protection.status === 'encrypted'
            ? 'Encryption is configured.'
            : 'No additional protection action is required from the current signals.'

    return {
      key: `${binding.sourceDataObjectVersionId}:${binding.sourceFieldId}`,
      attributeId: attribute?.id || binding.sourceFieldId,
      attributeName: attribute?.name || binding.sourceFieldName,
      sourceFieldType: attribute?.type || binding.sourceFieldType || 'text',
      sourceDataObjectVersionId: binding.sourceDataObjectVersionId,
      assetClassification: normalizedClassification || 'public',
      assetPriority: normalizedPriority || 'normal',
      signals: assetSignals.concat(classificationSignals.filter((signal) => !assetSignals.includes(signal))),
      maskingMethod: protection.maskingMethod,
      encryptionRequired: protection.encryptionRequired,
      encryptionKeyId: protection.encryptionKeyId,
      status: protection.status,
      statusDescription: protection.statusDescription,
      recommendation,
      needsProtection,
      target: attribute ? findDefinitionMappingTarget(binding.sourceDataObjectVersionId, attribute.id, products, standaloneDatasets) : null,
    }
  })
}

export const summarizeProtectionReview = (rows: DataAssetProtectionReviewRow[]): DataAssetProtectionSummary => {
  const reviewableRows = rows.filter((row) => row.status !== 'unavailable')
  const protectedRows = reviewableRows.filter((row) => row.status === 'masked' || row.status === 'encrypted')
  const unprotectedRows = rows.filter((row) => row.needsProtection && row.status === 'unprotected')
  const unavailableSensitiveRows = rows.filter((row) => row.needsProtection && row.status === 'unavailable')
  const unavailableRows = rows.filter((row) => row.status === 'unavailable')

  let advice = 'No protection advice is triggered by the current classification signals.'
  if (rows.some((row) => row.needsProtection)) {
    advice = unprotectedRows.length > 0
      ? `${unprotectedRows.length} attribute${unprotectedRows.length === 1 ? '' : 's'} should be protected through masking or encryption.`
      : unavailableSensitiveRows.length > 0
        ? `${unavailableSensitiveRows.length} sensitive attribute${unavailableSensitiveRows.length === 1 ? '' : 's'} could not be verified because source attribute details were not loaded.`
        : `${protectedRows.length} attribute${protectedRows.length === 1 ? '' : 's'} are already protected through masking or encryption.`
  }

  return {
    advice,
    sensitiveCount: rows.filter((row) => row.needsProtection).length,
    protectedCount: protectedRows.length,
    unprotectedCount: unprotectedRows.length,
    unavailableCount: unavailableRows.length,
  }
}

const emptyAssetForm = (): AssetFormState => ({
  id: '',
  name: '',
  description: '',
  workspaceId: '',
  status: 'draft',
  currentVersionId: '',
  sourceObjectVersionIdsText: '',
  businessContextDatasetId: '',
  businessContextDataProductId: '',
  businessContextDomain: '',
  businessContextOwner: '',
  businessContextPurpose: '',
  businessContextSteward: '',
  businessContextCriticality: '',
  businessContextTagsText: '',
  businessContextBusinessDefinitionsText: '',
  businessContextLineageReferencesText: '',
  businessContextConsumersText: '',
})

export const toAssetFormState = (asset: DataAssetSummary): AssetFormState => ({
  id: asset.id,
  name: asset.name,
  description: asset.description,
  workspaceId: asset.workspaceId,
  status: asset.status,
  currentVersionId: asset.currentVersionId || '',
  sourceObjectVersionIdsText: stringifyVersionIds(asset.sourceObjectVersionIds || []),
  businessContextDatasetId: asset.businessContext?.datasetId || '',
  businessContextDataProductId: asset.businessContext?.dataProductId || '',
  businessContextDomain: asset.businessContext?.domain || '',
  businessContextOwner: asset.businessContext?.owner || '',
  businessContextPurpose: asset.businessContext?.purpose || '',
  businessContextSteward: asset.businessContext?.steward || '',
  businessContextCriticality: asset.businessContext?.criticality || '',
  businessContextTagsText: stringifyVersionIds(asset.businessContext?.tags || []),
  businessContextBusinessDefinitionsText: stringifyVersionIds(asset.businessContext?.businessDefinitions || []),
  businessContextLineageReferencesText: stringifyVersionIds(asset.businessContext?.lineageReferences || []),
  businessContextConsumersText: stringifyVersionIds(asset.businessContext?.consumers || []),
})

const emptyVersionForm = (): VersionFormState => ({
  id: '',
  version: '1',
  createdAt: '',
  sourceBindings: [],
  filters: [],
  derivedFields: [],
  uploadPreview: {
    fileName: '',
    fileFormat: '',
    sourceUri: '',
    columns: [],
  },
})

const newBinding = (): DataAssetSourceBinding => ({
  sourceDataObjectVersionId: '',
  sourceFieldId: '',
  sourceFieldName: '',
  sourceFieldType: 'text',
  nullable: true,
})

const newFilter = (): DataAssetFilter => ({
  expression: '',
  enabled: true,
  description: '',
})

const newDerivedField = (): DataAssetDerivedField => ({
  name: '',
  expression: '',
  dataType: 'text',
  nullable: null,
  sourceFieldIds: [],
})

const newPreviewColumn = (): DataAssetUploadPreviewColumn => ({
  name: '',
  dataType: 'text',
  nullable: true,
})

const normalizePreviewName = (value: unknown, fallbackIndex: number): string => {
  const normalized = String(value ?? '').trim()
  return normalized || `column_${fallbackIndex + 1}`
}

const inferPreviewDataType = (value: unknown): string => {
  if (value === null || value === undefined || value === '') {
    return 'text'
  }
  if (typeof value === 'boolean') {
    return 'boolean'
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? 'integer' : 'number'
  }
  if (typeof value === 'string') {
    const normalized = value.trim()
    if (!normalized) {
      return 'text'
    }
    if (/^(true|false)$/i.test(normalized)) {
      return 'boolean'
    }
    if (/^-?\d+$/.test(normalized)) {
      return 'integer'
    }
    if (/^-?\d*\.\d+$/.test(normalized)) {
      return 'number'
    }
    if (!Number.isNaN(Date.parse(normalized)) && /\d{4}-\d{2}-\d{2}/.test(normalized)) {
      return 'date-time'
    }
    return 'text'
  }
  if (Array.isArray(value)) {
    return 'array'
  }
  if (typeof value === 'object') {
    return 'object'
  }
  return 'text'
}

const parseDelimitedRows = (text: string, delimiter: string): string[][] => {
  const rows: string[][] = []
  let currentRow: string[] = []
  let currentCell = ''
  let inQuotes = false

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index]
    const nextCharacter = text[index + 1]

    if (inQuotes) {
      if (character === '"' && nextCharacter === '"') {
        currentCell += '"'
        index += 1
        continue
      }
      if (character === '"') {
        inQuotes = false
        continue
      }
      currentCell += character
      continue
    }

    if (character === '"') {
      inQuotes = true
      continue
    }
    if (character === delimiter) {
      currentRow.push(currentCell)
      currentCell = ''
      continue
    }
    if (character === '\n' || character === '\r') {
      if (character === '\r' && nextCharacter === '\n') {
        index += 1
      }
      currentRow.push(currentCell)
      rows.push(currentRow)
      currentRow = []
      currentCell = ''
      continue
    }
    currentCell += character
  }

  currentRow.push(currentCell)
  rows.push(currentRow)

  return rows.filter((row) => row.some((cell) => cell.trim().length > 0))
}

const flattenJsonRecord = (value: unknown, prefix = '', target: Record<string, unknown> = {}): Record<string, unknown> => {
  if (value === null || value === undefined) {
    if (prefix) {
      target[prefix] = null
    }
    return target
  }

  if (Array.isArray(value)) {
    if (prefix) {
      target[prefix] = value
    }
    return target
  }

  if (typeof value !== 'object') {
    if (prefix) {
      target[prefix] = value
    }
    return target
  }

  Object.entries(value as Record<string, unknown>).forEach(([key, childValue]) => {
    const nextPrefix = prefix ? `${prefix}.${key}` : key
    flattenJsonRecord(childValue, nextPrefix, target)
  })

  return target
}

const isJsonSchemaLike = (value: unknown): value is Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }

  const schema = value as Record<string, unknown>
  return Boolean(
    schema.$schema ||
      schema.properties ||
      schema.items ||
      schema.definitions ||
      schema.$defs
  )
}

const collectSchemaColumns = (
  schema: unknown,
  prefix = '',
  parentNullable = false
): DataAssetUploadPreviewColumn[] => {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) {
    return [
      {
        name: prefix || 'value',
        dataType: inferPreviewDataType(schema),
        nullable: parentNullable,
      },
    ]
  }

  const schemaObject = schema as Record<string, unknown>
  const rawType = schemaObject.type
  const declaredType = Array.isArray(rawType)
    ? rawType.find((item) => typeof item === 'string' && item !== 'null')
    : rawType
  const typeName = typeof declaredType === 'string' ? declaredType : ''
  const nullable = parentNullable || (Array.isArray(rawType) && rawType.includes('null'))
  const format = typeof schemaObject.format === 'string' ? schemaObject.format : ''

  if (typeName === 'object' || schemaObject.properties) {
    const required = new Set(Array.isArray(schemaObject.required) ? schemaObject.required.map(String) : [])
    const properties = schemaObject.properties && typeof schemaObject.properties === 'object'
      ? (schemaObject.properties as Record<string, unknown>)
      : {}

    return Object.entries(properties).flatMap(([key, propertySchema]) =>
      collectSchemaColumns(propertySchema, prefix ? `${prefix}.${key}` : key, nullable || !required.has(key))
    )
  }

  if (typeName === 'array' && schemaObject.items) {
    return collectSchemaColumns(schemaObject.items, prefix ? `${prefix}[]` : 'value', nullable)
  }

  const dataType = format === 'date-time' || format === 'date'
    ? format
    : typeName || inferPreviewDataType(schemaObject)

  return [
    {
      name: prefix || 'value',
      dataType: dataType || 'text',
      nullable,
    },
  ]
}

const deriveColumnsFromRecords = (records: Record<string, unknown>[]): DataAssetUploadPreviewColumn[] => {
  const columnNames = new Set<string>()
  records.forEach((record) => {
    Object.keys(record).forEach((key) => columnNames.add(key))
  })

  return [...columnNames].sort().map((name, index) => {
    const samples = records
      .map((record) => record[name])
      .filter((value) => value !== null && value !== undefined && String(value).trim() !== '')
    const sample = samples.length > 0 ? samples[0] : undefined
    return {
      name: normalizePreviewName(name, index),
      dataType: inferPreviewDataType(sample),
      nullable: records.some((record) => record[name] === null || record[name] === undefined || String(record[name]).trim() === ''),
    }
  })
}

const parseJsonPreview = (content: unknown): DataAssetUploadPreviewColumn[] => {
  if (isJsonSchemaLike(content)) {
    return collectSchemaColumns(content)
  }

  if (Array.isArray(content)) {
    if (content.length === 0) {
      return []
    }

    const flattenedRows = content.map((item) => {
      if (item !== null && typeof item === 'object' && !Array.isArray(item)) {
        return flattenJsonRecord(item)
      }
      return { value: item }
    })

    return deriveColumnsFromRecords(flattenedRows)
  }

  if (content && typeof content === 'object') {
    return deriveColumnsFromRecords([flattenJsonRecord(content)])
  }

  return [
    {
      name: 'value',
      dataType: inferPreviewDataType(content),
      nullable: true,
    },
  ]
}

const buildUploadPreviewFromRows = (
  fileName: string,
  fileFormat: string,
  sourceUri: string,
  rows: string[][]
): DataAssetUploadPreview => {
  if (rows.length === 0) {
    return { fileName, fileFormat, sourceUri, columns: [] }
  }

  const [headerRow, ...dataRows] = rows
  const normalizedHeaders = headerRow.map((header, index) => normalizePreviewName(header, index))
  if (dataRows.length === 0) {
    return {
      fileName,
      fileFormat,
      sourceUri,
      columns: normalizedHeaders.map((name) => ({
        name,
        dataType: 'text',
        nullable: true,
      })),
    }
  }

  const records = dataRows.map((row) => {
    const record: Record<string, unknown> = {}
    normalizedHeaders.forEach((header, index) => {
      record[header] = row[index] ?? ''
    })
    return record
  })

  return {
    fileName,
    fileFormat,
    sourceUri,
    columns: deriveColumnsFromRecords(records),
  }
}

const readFileAsText = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
    reader.readAsText(file)
  })

const readFileAsArrayBuffer = (file: File): Promise<ArrayBuffer> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
    reader.readAsArrayBuffer(file)
  })

const createUploadPreviewFromFile = async (file: File): Promise<DataAssetUploadPreview> => {
  const lowerName = file.name.toLowerCase()
  const sourceUri = `uploaded://${file.name}`

  if (lowerName.endsWith('.csv')) {
    const text = await readFileAsText(file)
    return buildUploadPreviewFromRows(file.name, 'csv', sourceUri, parseDelimitedRows(text, ','))
  }

  if (lowerName.endsWith('.tsv')) {
    const text = await readFileAsText(file)
    return buildUploadPreviewFromRows(file.name, 'tsv', sourceUri, parseDelimitedRows(text, '\t'))
  }

  if (lowerName.endsWith('.xlsx') || lowerName.endsWith('.xls')) {
    const workbook = XLSX.read(await readFileAsArrayBuffer(file), { type: 'array' })
    const firstSheetName = workbook.SheetNames[0]
    if (!firstSheetName) {
      throw new Error('Excel file does not contain any sheets')
    }

    const sheet = workbook.Sheets[firstSheetName]
    const matrix = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, blankrows: false, defval: '' }) as unknown[][]
    const rows = matrix.map((row) => row.map((cell) => String(cell ?? '')))
    return buildUploadPreviewFromRows(file.name, 'xlsx', sourceUri, rows)
  }

  if (lowerName.endsWith('.json')) {
    const text = await readFileAsText(file)
    const parsed = JSON.parse(text)
    const columns = parseJsonPreview(parsed)
    return {
      fileName: file.name,
      fileFormat: isJsonSchemaLike(parsed) ? 'jsonschema' : 'json',
      sourceUri,
      columns,
    }
  }

  throw new Error('Unsupported upload format. Use CSV, TSV, XLSX, or JSON/JSON Schema.')
}

const buildHeaders = (token: string | null): HeadersInit => ({
  'Content-Type': 'application/json',
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
})

const parseError = async (response: Response): Promise<string> => {
  const fallback = `${response.status} ${response.statusText}`.trim()
  try {
    const body = await response.json()
    if (typeof body === 'string') {
      return body
    }
    if (body && typeof body === 'object') {
      if (typeof (body as Record<string, unknown>).detail === 'string') {
        return String((body as Record<string, unknown>).detail)
      }
      const error = (body as Record<string, unknown>).error
      const message = (body as Record<string, unknown>).message
      const parts = [error, message].filter(Boolean).map(String)
      if (parts.length > 0) {
        return parts.join(': ')
      }
      return JSON.stringify(body)
    }
  } catch {
    return fallback
  }
  return fallback
}

const requestJson = async <T,>(url: string, init: RequestInit = {}): Promise<T> => {
  const response = await fetch(url, init)
  if (!response.ok) {
    const error = new Error(await parseError(response)) as ApiError
    throw error
  }
  return (await response.json()) as T
}

const stringifyVersionIds = (value: string[]): string => value.join(', ')

const normalizeList = (value: string): string[] =>
  value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

const slugifyDataAssetId = (value: string): string =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

const suggestDataAssetId = (name: string, workspaceId: string): string => {
  const normalizedName = slugifyDataAssetId(name)
  if (normalizedName) {
    return normalizedName
  }

  const normalizedWorkspace = slugifyDataAssetId(workspaceId)
  if (normalizedWorkspace) {
    return `${normalizedWorkspace}-asset`
  }

  return 'data-asset'
}

const mergeUniqueValues = (currentValues: string[], nextValues: string[]): string[] => {
  const merged = new Set<string>()
  currentValues.forEach((value) => merged.add(value))
  nextValues.forEach((value) => merged.add(value))
  return Array.from(merged)
}

const lineageKindLabel = (kind: string): string => {
  switch (kind) {
    case 'data_product':
      return 'Data product'
    case 'data_set':
      return 'Data set'
    case 'data_object':
      return 'Data object'
    case 'data_object_version':
      return 'Source version'
    case 'rule':
      return 'Rule'
    case 'monitor_schedule':
      return 'Monitor'
    case 'incident':
      return 'Incident'
    default:
      return kind.replaceAll('_', ' ')
  }
}

const groupLineageNodes = (nodes: DataAssetLineageNode[]): DataAssetLineageNode[][] => {
  const order = ['data_product', 'data_set', 'data_object', 'data_object_version', 'rule', 'monitor_schedule', 'incident']
  const grouped = new Map<string, DataAssetLineageNode[]>()
  for (const node of nodes) {
    const key = node.kind || 'unknown'
    const current = grouped.get(key) || []
    current.push(node)
    grouped.set(key, current)
  }

  return order
    .filter((kind) => grouped.has(kind))
    .map((kind) => (grouped.get(kind) || []).slice().sort((left, right) => left.name.localeCompare(right.name)))
}

export const toAssetPayload = (form: AssetFormState) => {
  return camelToSnake({
    id: form.id.trim(),
    name: form.name.trim(),
    description: form.description.trim(),
    workspaceId: form.workspaceId.trim(),
    status: form.status.trim() || 'draft',
    currentVersionId: form.currentVersionId.trim() || null,
    sourceObjectVersionIds: normalizeList(form.sourceObjectVersionIdsText),
    businessContext: {
      datasetId: form.businessContextDatasetId.trim(),
      dataProductId: form.businessContextDataProductId.trim(),
      domain: form.businessContextDomain.trim(),
      owner: form.businessContextOwner.trim(),
      purpose: form.businessContextPurpose.trim(),
      steward: form.businessContextSteward.trim(),
      criticality: form.businessContextCriticality.trim(),
      tags: normalizeList(form.businessContextTagsText),
      businessDefinitions: normalizeList(form.businessContextBusinessDefinitionsText),
      lineageReferences: normalizeList(form.businessContextLineageReferencesText),
      consumers: normalizeList(form.businessContextConsumersText),
    },
  })
}

const toVersionPayload = (form: VersionFormState) => {
  return camelToSnake({
    id: form.id.trim(),
    version: Number(form.version) || 1,
    createdAt: form.createdAt.trim() || undefined,
    sourceBindings: form.sourceBindings
      .map((binding) => ({
        sourceDataObjectVersionId: binding.sourceDataObjectVersionId.trim(),
        sourceFieldId: binding.sourceFieldId.trim(),
        sourceFieldName: binding.sourceFieldName.trim(),
        sourceFieldType: binding.sourceFieldType.trim() || 'text',
        nullable: Boolean(binding.nullable),
      }))
      .filter((binding) => binding.sourceDataObjectVersionId && binding.sourceFieldId),
    filters: form.filters
      .map((filter) => ({
        expression: filter.expression.trim(),
        enabled: Boolean(filter.enabled),
        description: filter.description?.trim() || null,
      }))
      .filter((filter) => filter.expression),
    derivedFields: form.derivedFields
      .map((field) => ({
        name: field.name.trim(),
        expression: field.expression.trim(),
        dataType: field.dataType?.trim() || null,
        nullable: field.nullable,
        sourceFieldIds: field.sourceFieldIds,
      }))
      .filter((field) => field.name && field.expression),
    uploadPreview: {
      fileName: form.uploadPreview.fileName?.trim() || null,
      fileFormat: form.uploadPreview.fileFormat?.trim() || null,
      sourceUri: form.uploadPreview.sourceUri?.trim() || null,
      columns: form.uploadPreview.columns
        .map((column) => ({
          name: column.name.trim(),
          dataType: column.dataType.trim() || 'text',
          nullable: Boolean(column.nullable),
        }))
        .filter((column) => column.name),
    },
  })
}

type DataAssetsBuilderProps = {
  onNavigate?: (target: string) => void
}

export const DataAssetsBuilder: React.FC<DataAssetsBuilderProps> = ({ onNavigate }) => {
  const settings = useSettings()
  const auth = useAuth()
  const currentWorkspaceId = auth.currentWorkspaceId || ''
  const {
    filteredProducts,
    standaloneDatasets,
    loadDatasets,
    loadDataObjects,
    loadVersions: loadCatalogVersions,
    loadAttributes: loadCatalogAttributes,
    isLoadingDatasets,
    isLoadingObjects,
    isLoadingVersions,
    isLoadingAttributes,
  } = useDataProduct()
  const apiBase = useMemo(() => toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl), [settings.applicationSettings?.apiBaseUrl])
  const token = useMemo(() => getAuthToken(), [auth.isAuthenticated, auth.currentWorkspaceId])

  const [assets, setAssets] = useState<DataAssetSummary[]>([])
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [versions, setVersions] = useState<DataAssetVersion[]>([])
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [assetForm, setAssetForm] = useState<AssetFormState>(emptyAssetForm())
  const [assetIdTouched, setAssetIdTouched] = useState(false)
  const [versionForm, setVersionForm] = useState<VersionFormState>(emptyVersionForm())
  const [isNewAssetDraft, setIsNewAssetDraft] = useState(false)
  const [uploadPreviewLoading, setUploadPreviewLoading] = useState(false)
  const [sourceProductId, setSourceProductId] = useState('')
  const [sourceDatasetId, setSourceDatasetId] = useState('')
  const [sourceObjectId, setSourceObjectId] = useState('')
  const [sourceVersionId, setSourceVersionId] = useState('')
  const [sourceAttributeId, setSourceAttributeId] = useState('')
  const [validationResult, setValidationResult] = useState<DataAssetValidation | null>(null)
  const [generatedPayload, setGeneratedPayload] = useState<Record<string, unknown> | null>(null)
  const [sampleCount, setSampleCount] = useState('10')
  const [contractAnalysis, setContractAnalysis] = useState<DataAssetContractAnalysis | null>(null)
  const [lineage, setLineage] = useState<DataAssetLineage | null>(null)
  const [governanceDiscovery, setGovernanceDiscovery] = useState<DataAssetGovernanceDiscovery | null>(null)
  const [sourceAttributesByVersionId, setSourceAttributesByVersionId] = useState<Record<string, DataAttribute[] | null>>({})
  const [reviewComments, setReviewComments] = useState('')
  const [loadingContractAnalysis, setLoadingContractAnalysis] = useState(false)
  const [loadingLineage, setLoadingLineage] = useState(false)
  const [loadingGovernanceDiscovery, setLoadingGovernanceDiscovery] = useState(false)
  const [loadingProtectionReview, setLoadingProtectionReview] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingVersions, setLoadingVersions] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedAssetId) || null,
    [assets, selectedAssetId]
  )
  const selectedVersion = useMemo(
    () => versions.find((version) => version.id === selectedVersionId) || null,
    [versions, selectedVersionId]
  )
  const sourceProduct = useMemo<DataProduct | null>(() => {
    return filteredProducts.find((product) => product.id === sourceProductId) || null
  }, [filteredProducts, sourceProductId])
  const sourceDatasetOptions = useMemo<DataSet[]>(() => {
    if (sourceProduct) {
      return sourceProduct.datasets && sourceProduct.datasets.length > 0 ? sourceProduct.datasets : []
    }
    return standaloneDatasets
  }, [sourceProduct, standaloneDatasets])
  const sourceDataset = useMemo<DataSet | null>(() => {
    return sourceDatasetOptions.find((dataset) => dataset.id === sourceDatasetId) || null
  }, [sourceDatasetOptions, sourceDatasetId])
  const sourceObjectOptions = useMemo<DataObject[]>(() => {
    return sourceDataset?.dataObjects || []
  }, [sourceDataset])
  const sourceObject = useMemo<DataObject | null>(() => {
    return sourceObjectOptions.find((dataObject) => dataObject.id === sourceObjectId) || null
  }, [sourceObjectOptions, sourceObjectId])
  const sourceVersionOptions = useMemo<DataObjectVersion[]>(() => {
    return sourceObject?.versions || []
  }, [sourceObject])
  const sourceVersion = useMemo<DataObjectVersion | null>(() => {
    return sourceVersionOptions.find((version) => version.id === sourceVersionId) || null
  }, [sourceVersionOptions, sourceVersionId])
  const sourceAttributeOptions = useMemo<DataAttribute[]>(() => {
    return sourceVersion?.attributes || []
  }, [sourceVersion])
  const sourceAttribute = useMemo<DataAttribute | null>(() => {
    return sourceAttributeOptions.find((attribute) => attribute.id === sourceAttributeId) || null
  }, [sourceAttributeOptions, sourceAttributeId])
  const assetSourceVersionIds = useMemo(() => normalizeList(assetForm.sourceObjectVersionIdsText), [assetForm.sourceObjectVersionIdsText])
  const assetIdSuggestion = useMemo(() => suggestDataAssetId(assetForm.name, currentWorkspaceId), [assetForm.name, currentWorkspaceId])
  const assetIdSuggestionRef = useRef('')
  const assetContractImportInputRef = useRef<HTMLInputElement | null>(null)
  const protectionReviewRows = useMemo(() => {
    return buildProtectionReviewRows(
      selectedVersion,
      sourceAttributesByVersionId,
      lineage?.classificationView?.classification || 'public',
      governanceDiscovery?.priority || 'normal',
      filteredProducts,
      standaloneDatasets,
    )
  }, [filteredProducts, governanceDiscovery?.priority, lineage?.classificationView?.classification, selectedVersion, sourceAttributesByVersionId, standaloneDatasets])
  const protectionReviewSummary = useMemo(() => summarizeProtectionReview(protectionReviewRows), [protectionReviewRows])

  useEffect(() => {
    if (!selectedVersion || selectedVersion.sourceBindings.length === 0) {
      setLoadingProtectionReview(false)
      return
    }

    const sourceVersionIds = Array.from(new Set(
      selectedVersion.sourceBindings
        .map((binding) => binding.sourceDataObjectVersionId)
        .filter((versionId) => Boolean(versionId)),
    ))
    const missingVersionIds = sourceVersionIds.filter((versionId) => sourceAttributesByVersionId[versionId] === undefined)

    if (missingVersionIds.length === 0) {
      setLoadingProtectionReview(false)
      return
    }

    let cancelled = false
    setLoadingProtectionReview(true)

    void Promise.all(
      missingVersionIds.map(async (versionId) => [versionId, await loadCatalogAttributes(versionId)] as const),
    ).then((results) => {
      if (cancelled) {
        return
      }

      setSourceAttributesByVersionId((current) => {
        const next = { ...current }
        for (const [versionId, attributes] of results) {
          next[versionId] = attributes
        }
        return next
      })
    }).finally(() => {
      if (!cancelled) {
        setLoadingProtectionReview(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [loadCatalogAttributes, selectedVersion, sourceAttributesByVersionId])

  useEffect(() => {
    if (!isNewAssetDraft || !currentWorkspaceId) {
      return
    }

    setAssetForm((current) => {
      if (current.workspaceId === currentWorkspaceId) {
        return current
      }

      return {
        ...current,
        workspaceId: currentWorkspaceId,
      }
    })
  }, [currentWorkspaceId, isNewAssetDraft])

  useEffect(() => {
    if (!isNewAssetDraft || assetIdTouched) {
      return
    }

    const trimmedName = assetForm.name.trim()
    if (!trimmedName) {
      assetIdSuggestionRef.current = ''
      return
    }

    const currentAssetId = assetForm.id.trim()
    const shouldReplaceSuggestedId = !currentAssetId || currentAssetId === assetIdSuggestionRef.current

    if (shouldReplaceSuggestedId && currentAssetId !== assetIdSuggestion) {
      setAssetForm((current) => ({
        ...current,
        id: assetIdSuggestion,
      }))
    }

    assetIdSuggestionRef.current = assetIdSuggestion
  }, [assetForm.id, assetForm.name, assetIdSuggestion, assetIdTouched, isNewAssetDraft])

  const openDefinitionMappingTarget = useCallback((target: DefinitionMappingTarget) => {
    try {
      sessionStorage.setItem('dq-definition-mapping-target', JSON.stringify(target))
    } catch {
      setError('Unable to prepare the protection editor target.')
      return
    }

    onNavigate?.('definition-mappings')
  }, [onNavigate])

  const beginNewAssetDraft = useCallback(() => {
    setIsNewAssetDraft(true)
    setSelectedAssetId(null)
    setAssetIdTouched(false)
    assetIdSuggestionRef.current = ''
    setAssetForm({
      ...emptyAssetForm(),
      workspaceId: currentWorkspaceId,
    })
    setSelectedVersionId(null)
    setVersionForm(emptyVersionForm())
    setContractAnalysis(null)
    setLineage(null)
    setGovernanceDiscovery(null)
    setReviewComments('')
    setValidationResult(null)
    setGeneratedPayload(null)
  }, [currentWorkspaceId])

  const addSelectedSourceVersionToAsset = useCallback(() => {
    if (!sourceVersion?.id) {
      return
    }

    setAssetForm((current) => ({
      ...current,
      sourceObjectVersionIdsText: mergeUniqueValues(normalizeList(current.sourceObjectVersionIdsText), [sourceVersion.id]).join(', '),
    }))
  }, [sourceVersion?.id])

  const removeAssetSourceVersionId = useCallback((versionId: string) => {
    const normalizedVersionId = String(versionId || '').trim()
    if (!normalizedVersionId) {
      return
    }

    setAssetForm((current) => ({
      ...current,
      sourceObjectVersionIdsText: normalizeList(current.sourceObjectVersionIdsText).filter((item) => item !== normalizedVersionId).join(', '),
    }))
  }, [])

  const loadContractAnalysis = useCallback(async (assetId: string) => {
    setLoadingContractAnalysis(true)
    setError(null)
    try {
      const payload = await requestJson<unknown>(`${apiBase}/data-assets/${encodeURIComponent(assetId)}/contract/analysis`, {
        headers: buildHeaders(token),
      })
      const normalized = snakeToCamel<DataAssetContractAnalysis>(payload)
      setContractAnalysis(normalized)
      setReviewComments(normalized.latestContractVersion?.reviewComments || '')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to load contract analysis')
    } finally {
      setLoadingContractAnalysis(false)
    }
  }, [apiBase, token])

  const loadLineage = useCallback(async (assetId: string) => {
    setLoadingLineage(true)
    setError(null)
    try {
      const payload = await requestJson<unknown>(`${apiBase}/data-assets/${encodeURIComponent(assetId)}/lineage`, {
        headers: buildHeaders(token),
      })
      const normalized = snakeToCamel<DataAssetLineage>(payload)
      setLineage(normalized)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to load Data Asset lineage')
      setLineage(null)
    } finally {
      setLoadingLineage(false)
    }
  }, [apiBase, token])

  const loadGovernanceDiscovery = useCallback(async (assetId: string) => {
    setLoadingGovernanceDiscovery(true)
    setError(null)
    try {
      const payload = await requestJson<unknown>(`${apiBase}/data-assets/${encodeURIComponent(assetId)}/governance-discovery`, {
        headers: buildHeaders(token),
      })
      const normalized = snakeToCamel<DataAssetGovernanceDiscovery>(payload)
      setGovernanceDiscovery(normalized)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to load Data Asset governance discovery')
      setGovernanceDiscovery(null)
    } finally {
      setLoadingGovernanceDiscovery(false)
    }
  }, [apiBase, token])

  const loadAssets = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await requestJson<unknown[]>(`${apiBase}/data-assets`, {
        headers: buildHeaders(token),
      })
      const normalized = snakeToCamel<DataAssetSummary[]>(payload)
      setAssets(normalized)
      if (normalized.length === 0) {
        setSelectedAssetId(null)
        setVersions([])
        setSelectedVersionId(null)
        setAssetForm(emptyAssetForm())
        setVersionForm(emptyVersionForm())
        setContractAnalysis(null)
        setLineage(null)
        setGovernanceDiscovery(null)
        setReviewComments('')
        setIsNewAssetDraft(false)
        setAssetIdTouched(false)
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to load Data Assets')
    } finally {
      setLoading(false)
    }
  }, [apiBase, token])

  const loadVersions = useCallback(async (assetId: string, preferredVersionId?: string | null) => {
    setLoadingVersions(true)
    setError(null)
    try {
      const payload = await requestJson<unknown[]>(`${apiBase}/data-assets/${encodeURIComponent(assetId)}/versions`, {
        headers: buildHeaders(token),
      })
      const normalized = snakeToCamel<DataAssetVersion[]>(payload)
      setVersions(normalized)
      const selected = normalized.find((version) => version.id === preferredVersionId)
        || normalized.find((version) => version.id === assets.find((asset) => asset.id === assetId)?.currentVersionId)
        || normalized[0]
        || null
      setSelectedVersionId(selected?.id || null)
      setVersionForm(selected ? toVersionFormState(selected) : emptyVersionForm())
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to load Data Asset versions')
    } finally {
      setLoadingVersions(false)
    }
  }, [apiBase, assets, token])

  useEffect(() => {
    void loadAssets()
  }, [loadAssets])

  useEffect(() => {
    if (isNewAssetDraft) {
      return
    }

    if (assets.length === 0) {
      setSelectedAssetId(null)
      setVersions([])
      setSelectedVersionId(null)
      setVersionForm(emptyVersionForm())
      setLineage(null)
      setGovernanceDiscovery(null)
      return
    }

    const selected = selectedAssetId ? assets.find((asset) => asset.id === selectedAssetId) : null
    if (!selected) {
      setSelectedAssetId(assets[0].id)
      return
    }

    setAssetForm(toAssetFormState(selected))
    void loadVersions(selected.id, selected.currentVersionId)
    void loadContractAnalysis(selected.id)
    void loadLineage(selected.id)
    void loadGovernanceDiscovery(selected.id)
  }, [assets, isNewAssetDraft, loadContractAnalysis, loadGovernanceDiscovery, loadLineage, loadVersions, selectedAssetId])

  useEffect(() => {
    if (!selectedVersionId) {
      setVersionForm(emptyVersionForm())
      return
    }
    const selected = versions.find((version) => version.id === selectedVersionId)
    if (selected) {
      setVersionForm(toVersionFormState(selected))
    }
  }, [selectedVersionId, versions])

  useEffect(() => {
    if (filteredProducts.length === 0) {
      setSourceProductId('')
      return
    }

    if (!sourceProductId || !filteredProducts.some((product) => product.id === sourceProductId)) {
      setSourceProductId(filteredProducts[0].id)
    }
  }, [filteredProducts, sourceProductId])

  useEffect(() => {
    if (!sourceProductId) {
      return
    }

    void loadDatasets(sourceProductId)
  }, [loadDatasets, sourceProductId])

  useEffect(() => {
    if (sourceDatasetOptions.length === 0) {
      setSourceDatasetId('')
      return
    }

    if (!sourceDatasetId || !sourceDatasetOptions.some((dataset) => dataset.id === sourceDatasetId)) {
      setSourceDatasetId(sourceDatasetOptions[0].id)
    }
  }, [sourceDatasetId, sourceDatasetOptions])

  useEffect(() => {
    if (!sourceDatasetId) {
      return
    }

    void loadDataObjects(sourceDatasetId)
  }, [loadDataObjects, sourceDatasetId])

  useEffect(() => {
    if (sourceObjectOptions.length === 0) {
      setSourceObjectId('')
      return
    }

    if (!sourceObjectId || !sourceObjectOptions.some((dataObject) => dataObject.id === sourceObjectId)) {
      setSourceObjectId(sourceObjectOptions[0].id)
    }
  }, [sourceObjectId, sourceObjectOptions])

  useEffect(() => {
    if (!sourceObjectId) {
      return
    }

    void loadCatalogVersions(sourceObjectId)
  }, [loadCatalogVersions, sourceObjectId])

  useEffect(() => {
    if (sourceVersionOptions.length === 0) {
      setSourceVersionId('')
      return
    }

    if (!sourceVersionId || !sourceVersionOptions.some((version) => version.id === sourceVersionId)) {
      setSourceVersionId(sourceVersionOptions[0].id)
    }
  }, [sourceVersionId, sourceVersionOptions])

  useEffect(() => {
    if (!sourceVersionId) {
      return
    }

    void loadCatalogAttributes(sourceVersionId)
  }, [loadCatalogAttributes, sourceVersionId])

  useEffect(() => {
    if (sourceAttributeOptions.length === 0) {
      setSourceAttributeId('')
      return
    }

    if (!sourceAttributeId || !sourceAttributeOptions.some((attribute) => attribute.id === sourceAttributeId)) {
      setSourceAttributeId(sourceAttributeOptions[0].id)
    }
  }, [sourceAttributeId, sourceAttributeOptions])

  const selectAsset = async (asset: DataAssetSummary) => {
    setIsNewAssetDraft(false)
    setAssetIdTouched(false)
    setSelectedAssetId(asset.id)
    setValidationResult(null)
    setGeneratedPayload(null)
    setAssetForm(toAssetFormState(asset))
    await loadVersions(asset.id, asset.currentVersionId)
    await loadContractAnalysis(asset.id)
    await loadLineage(asset.id)
  }

  const createAsset = async () => {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      setIsNewAssetDraft(false)
      const payload = toAssetPayload(assetForm)
      const created = await requestJson<DataAssetSummary>(`${apiBase}/data-assets`, {
        method: 'POST',
        headers: buildHeaders(token),
        body: JSON.stringify(payload),
      })
      setMessage(`Created Data Asset ${created.id}`)
      await loadAssets()
      await selectAsset(created)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to create Data Asset')
    } finally {
      setSaving(false)
    }
  }

  const updateAsset = async () => {
    if (!selectedAssetId) {
      return
    }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      setIsNewAssetDraft(false)
      const payload = toAssetPayload(assetForm)
      const updated = await requestJson<DataAssetSummary>(`${apiBase}/data-assets/${encodeURIComponent(selectedAssetId)}`, {
        method: 'PUT',
        headers: buildHeaders(token),
        body: JSON.stringify(payload),
      })
      setMessage(`Updated Data Asset ${updated.id}`)
      await loadAssets()
      await selectAsset(updated)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to update Data Asset')
    } finally {
      setSaving(false)
    }
  }

  const deleteAsset = async () => {
    if (!selectedAssetId) {
      return
    }
    if (!window.confirm(`Delete Data Asset ${selectedAssetId}?`)) {
      return
    }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      setIsNewAssetDraft(false)
      await requestJson<{ ok: boolean }>(`${apiBase}/data-assets/${encodeURIComponent(selectedAssetId)}`, {
        method: 'DELETE',
        headers: buildHeaders(token),
      })
      setMessage(`Deleted Data Asset ${selectedAssetId}`)
      setSelectedAssetId(null)
      setSelectedVersionId(null)
      setVersions([])
      setAssetForm(emptyAssetForm())
      setVersionForm(emptyVersionForm())
      setContractAnalysis(null)
      setLineage(null)
      setReviewComments('')
      setAssetIdTouched(false)
      await loadAssets()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to delete Data Asset')
    } finally {
      setSaving(false)
    }
  }

  const createVersion = async () => {
    if (!selectedAssetId) {
      return
    }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const payload = toVersionPayload(versionForm)
      const created = await requestJson<DataAssetVersion>(`${apiBase}/data-assets/${encodeURIComponent(selectedAssetId)}/versions`, {
        method: 'POST',
        headers: buildHeaders(token),
        body: JSON.stringify(payload),
      })
      setMessage(`Created version ${created.id}`)
      await loadAssets()
      await loadVersions(selectedAssetId, created.id)
      await loadLineage(selectedAssetId)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to create Data Asset version')
    } finally {
      setSaving(false)
    }
  }

  const validateAsset = async () => {
    if (!selectedAssetId) {
      return
    }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const payload = await requestJson<DataAssetValidation>(`${apiBase}/data-assets/${encodeURIComponent(selectedAssetId)}/validate`, {
        method: 'POST',
        headers: buildHeaders(token),
      })
      setValidationResult(snakeToCamel<DataAssetValidation>(payload))
      setMessage(`Validated Data Asset ${selectedAssetId}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to validate Data Asset')
    } finally {
      setSaving(false)
    }
  }

  const reviewContract = async (reviewStatus: 'approved' | 'rejected') => {
    if (!selectedAssetId) {
      return
    }

    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const payload = await requestJson<{ success: boolean }>(`${apiBase}/data-assets/${encodeURIComponent(selectedAssetId)}/contract/review`, {
        method: 'POST',
        headers: buildHeaders(token),
        body: JSON.stringify({
          review_status: reviewStatus,
          review_comments: reviewComments.trim() || undefined,
        }),
      })
      if (!payload.success) {
        throw new Error('Contract review did not complete successfully')
      }
      setMessage(`Marked contract ${reviewStatus} for ${selectedAssetId}`)
      await loadAssets()
      await loadVersions(selectedAssetId, selectedVersionId)
      await loadContractAnalysis(selectedAssetId)
      await loadLineage(selectedAssetId)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to review Data Asset contract')
    } finally {
      setSaving(false)
    }
  }

  const generateTestData = async () => {
    if (!selectedAssetId) {
      return
    }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const payload = await requestJson<Record<string, unknown>>(
        `${apiBase}/data-assets/${encodeURIComponent(selectedAssetId)}/generate-test-data`,
        {
          method: 'POST',
          headers: buildHeaders(token),
          body: JSON.stringify({ sample_count: Number(sampleCount) || 10 }),
        }
      )
      setGeneratedPayload(snakeToCamel<Record<string, unknown>>(payload))
      setMessage(`Generated test data for ${selectedAssetId}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to generate test data')
    } finally {
      setSaving(false)
    }
  }

  const importUploadPreview = async (file: File) => {
    setUploadPreviewLoading(true)
    setError(null)
    setMessage(null)
    try {
      const preview = await createUploadPreviewFromFile(file)
      updateSelectedVersion({ uploadPreview: preview })
      setMessage(`Loaded schema preview from ${file.name}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to import schema preview')
    } finally {
      setUploadPreviewLoading(false)
    }
  }

  const addSourceBindingFromSelection = () => {
    if (!sourceVersion || !sourceAttribute) {
      return
    }

    updateSelectedVersion({
      sourceBindings: [
        ...versionForm.sourceBindings,
        {
          sourceDataObjectVersionId: sourceVersion.id,
          sourceFieldId: sourceAttribute.id,
          sourceFieldName: sourceAttribute.name,
          sourceFieldType: sourceAttribute.type,
          nullable: sourceAttribute.nullable,
          schemaLocked: true,
        },
      ],
    })
  }

  const downloadContract = async (format: 'yaml' | 'json' = 'yaml') => {
    if (!selectedAsset?.dataContractDownloadUrl) {
      return
    }

    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const response = await fetch(`${apiBase}${selectedAsset.dataContractDownloadUrl}?format=${format}`, {
        headers: buildHeaders(token),
      })
      if (!response.ok) {
        throw new Error(await parseError(response))
      }

      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      const downloadLink = document.createElement('a')
      downloadLink.href = blobUrl
      downloadLink.download = `${selectedAsset.id}.odcs.${format === 'json' ? 'json' : 'yaml'}`
      document.body.appendChild(downloadLink)
      downloadLink.click()
      downloadLink.remove()
      URL.revokeObjectURL(blobUrl)
      setMessage(`Downloaded ${format.toUpperCase()} contract for ${selectedAsset.id}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to download data contract')
    } finally {
      setSaving(false)
    }
  }

  const importContract = async (file: File) => {
    if (!selectedAssetId) {
      return
    }

    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const contractText = await file.text()
      const payload = await requestJson<unknown>(`${apiBase}/data-assets/${encodeURIComponent(selectedAssetId)}/contract/import`, {
        method: 'POST',
        headers: buildHeaders(token),
        body: JSON.stringify({ contract_text: contractText }),
      })
      const normalized = snakeToCamel<DataAssetSummary>(payload)
      setSelectedAssetId(normalized.id)
      setAssetForm(toAssetFormState(normalized))
      setIsNewAssetDraft(false)
      setAssetIdTouched(true)
      setAssets((current) => current.map((asset) => (asset.id === normalized.id ? normalized : asset)))
      await loadAssets()
      await loadContractAnalysis(normalized.id)
      await loadLineage(normalized.id)
      await loadGovernanceDiscovery(normalized.id)
      setMessage(`Imported contract for ${normalized.id}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Failed to import data contract')
    } finally {
      setSaving(false)
    }
  }

  const onAssetContractImportChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) {
      return
    }
    await importContract(file)
  }

  const updateSelectedVersion = (nextVersion: Partial<VersionFormState>) => {
    setVersionForm((current) => ({ ...current, ...nextVersion }))
  }

  const sourceSelectionSummary = useMemo(() => {
    const parts = [
      sourceProduct?.name || sourceProduct?.id || null,
      sourceDataset?.name || sourceDataset?.id || null,
      sourceObject?.name || sourceObject?.id || null,
      sourceVersion ? `v${sourceVersion.version}` : null,
      sourceAttribute ? `${sourceAttribute.name} (${sourceAttribute.type})` : null,
    ].filter(Boolean)

    return parts.length > 0 ? parts.join(' / ') : 'No source selected.'
  }, [sourceAttribute, sourceDataset, sourceObject, sourceProduct, sourceVersion])

  const contractBreakingChanges = contractAnalysis?.comparison?.changes.filter((change) => change.severity === 'breaking') || []
  const conformanceIssues = contractAnalysis?.conformance.issues || []

  const stats = {
    assetCount: assets.length,
    versionCount: versions.length,
    bindingCount: versionForm.sourceBindings.length,
  }

  return (
    <div className="data-assets-page">
      <AdminPageHeader
        title="Data Asset Studio"
        subtitle="Create schema-only assets, version them, and resolve them for rule authoring or test data generation."
        actions={
          <>
            <SecondaryButton onClick={() => void loadAssets()} disabled={loading || saving}>
              Refresh
            </SecondaryButton>
            <PrimaryButton onClick={() => { beginNewAssetDraft() }} disabled={saving}>
              New Asset
            </PrimaryButton>
          </>
        }
        supplementary={
          <div className="data-assets-stats">
            <div className="data-assets-stat">
              <span>Assets</span>
              <strong>{stats.assetCount}</strong>
            </div>
            <div className="data-assets-stat">
              <span>Versions</span>
              <strong>{stats.versionCount}</strong>
            </div>
            <div className="data-assets-stat">
              <span>Bindings</span>
              <strong>{stats.bindingCount}</strong>
            </div>
          </div>
        }
      />

      <div className="data-assets-toolbar">
        <div className="data-assets-toolbar-copy">
          <p>Data Assets are DQ-owned business views. Source bindings stay reference-bound; derived fields stay authored.</p>
        </div>
        <div className="data-assets-toolbar-note">
          {selectedAsset ? <span>Editing {selectedAsset.name || selectedAsset.id}</span> : <span>Creating a new asset</span>}
        </div>
      </div>

      <div className="data-assets-guide">
        <div className="data-assets-guide-step">
          <span className="data-assets-guide-step-index">1</span>
          <div>
            <strong>Define identity</strong>
            <p>Asset ID is suggested from the name, and the workspace stays locked to the current workspace.</p>
          </div>
        </div>
        <div className="data-assets-guide-step">
          <span className="data-assets-guide-step-index">2</span>
          <div>
            <strong>Browse the catalog</strong>
            <p>Pick source versions from the catalog browser instead of typing IDs by hand.</p>
          </div>
        </div>
        <div className="data-assets-guide-step">
          <span className="data-assets-guide-step-index">3</span>
          <div>
            <strong>Review and refine</strong>
            <p>Use contract, lineage, governance, and version detail panels to validate the asset before saving.</p>
          </div>
        </div>
      </div>

      {message && <div className="data-assets-banner success">{message}</div>}
      {error && <div className="data-assets-banner error">{error}</div>}

      <section className="data-assets-panel" aria-label="Metadata browser assistant">
        <AgentChatPanel
          defaultAgentType="general"
          defaultPrompt="Help me inspect metadata for this data asset, including source bindings, lineage, governance signals, and contract implications. Suggest concrete questions, protection checks, or refinements before I save this asset."
          title="Metadata browser assistant"
          description="Use the existing dq-llm harness to explore catalog metadata, lineage, and governance context for the current Data Asset Studio view."
        />
      </section>

      <div className="data-assets-layout">
        <aside className="data-assets-sidebar">
          <div className="data-assets-panel-header">
            <h2>Assets</h2>
            <span>{loading ? 'Loading…' : `${assets.length} total`}</span>
          </div>
          <div className="data-assets-list">
            {assets.map((asset) => (
              <button
                key={asset.id}
                type="button"
                className={`data-assets-list-item ${asset.id === selectedAssetId ? 'is-selected' : ''}`}
                onClick={() => void selectAsset(asset)}
              >
                <span className="data-assets-list-item-title">{asset.name || asset.id}</span>
                <span className="data-assets-list-item-meta">{asset.id}</span>
                <span className="data-assets-list-item-meta">Version {asset.currentVersionId || 'draft'}</span>
              </button>
            ))}
            {!loading && assets.length === 0 && (
              <div className="data-assets-empty">No Data Assets yet. Create the first one on the right.</div>
            )}
          </div>
        </aside>

        <main className="data-assets-main">
          <section className="data-assets-panel">
            <div className="data-assets-panel-header">
              <h2>Asset Metadata</h2>
              <span>Canonical object and workspace binding</span>
            </div>
            <div className="data-assets-form-grid">
              <label>
                <span>Asset ID</span>
                <input
                  value={assetForm.id}
                  onChange={(event) => {
                    setAssetIdTouched(true)
                    setAssetForm((current) => ({ ...current, id: event.target.value }))
                  }}
                  placeholder={assetIdSuggestion}
                  disabled={Boolean(selectedAssetId)}
                />
                <span className="data-assets-helptext">Suggested: {assetIdSuggestion}</span>
              </label>
              <label>
                <span>Name</span>
                <input
                  value={assetForm.name}
                  onChange={(event) => setAssetForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Customer health"
                />
              </label>
              <label>
                <span>Workspace ID</span>
                <input
                  value={assetForm.workspaceId || currentWorkspaceId}
                  readOnly
                  placeholder={currentWorkspaceId || 'Current workspace'}
                />
                <span className="data-assets-helptext">This asset is created in the active workspace only.</span>
              </label>
              <label>
                <span>Status</span>
                <input
                  value={assetForm.status}
                  onChange={(event) => setAssetForm((current) => ({ ...current, status: event.target.value }))}
                  placeholder="draft"
                />
              </label>
              <label className="data-assets-form-wide">
                <span>Description</span>
                <textarea
                  value={assetForm.description}
                  onChange={(event) => setAssetForm((current) => ({ ...current, description: event.target.value }))}
                  placeholder="What does this Data Asset represent?"
                  rows={3}
                />
              </label>
              <label>
                <span>Business domain</span>
                <input
                  value={assetForm.businessContextDomain}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextDomain: event.target.value }))}
                  placeholder="Customer"
                />
              </label>
              <label>
                <span>Owner</span>
                <input
                  value={assetForm.businessContextOwner}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextOwner: event.target.value }))}
                  placeholder="data-owner@example.com"
                />
              </label>
              <label>
                <span>Data product ID</span>
                <input
                  value={assetForm.businessContextDataProductId}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextDataProductId: event.target.value }))}
                  placeholder="product-1"
                />
              </label>
              <label>
                <span>Dataset ID</span>
                <input
                  value={assetForm.businessContextDatasetId}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextDatasetId: event.target.value }))}
                  placeholder="dataset-1"
                />
              </label>
              <label>
                <span>Business steward</span>
                <input
                  value={assetForm.businessContextSteward}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextSteward: event.target.value }))}
                  placeholder="data-steward@example.com"
                />
              </label>
              <label>
                <span>Criticality</span>
                <input
                  value={assetForm.businessContextCriticality}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextCriticality: event.target.value }))}
                  placeholder="high"
                />
              </label>
              <label className="data-assets-form-wide">
                <span>Business purpose</span>
                <textarea
                  value={assetForm.businessContextPurpose}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextPurpose: event.target.value }))}
                  placeholder="Why does this asset exist?"
                  rows={2}
                />
              </label>
              <label className="data-assets-form-wide">
                <span>Tags</span>
                <input
                  value={assetForm.businessContextTagsText}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextTagsText: event.target.value }))}
                  placeholder="customer, regulated, pii"
                />
                <span className="data-assets-helptext">Use comma-separated tags that help drive metadata selectors and governance context.</span>
              </label>
              <label className="data-assets-form-wide">
                <span>Business definitions</span>
                <textarea
                  value={assetForm.businessContextBusinessDefinitionsText}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextBusinessDefinitionsText: event.target.value }))}
                  placeholder="Definition 1, Definition 2"
                  rows={2}
                />
                <span className="data-assets-helptext">Add one or more canonical business definitions, separated by commas.</span>
              </label>
              <label className="data-assets-form-wide">
                <span>Lineage references</span>
                <textarea
                  value={assetForm.businessContextLineageReferencesText}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextLineageReferencesText: event.target.value }))}
                  placeholder="dov-1, upstream-job-7"
                  rows={2}
                />
                <span className="data-assets-helptext">Capture upstream asset, object, or workflow references that explain the asset's lineage.</span>
              </label>
              <label className="data-assets-form-wide">
                <span>Consumers</span>
                <input
                  value={assetForm.businessContextConsumersText}
                  onChange={(event) => setAssetForm((current) => ({ ...current, businessContextConsumersText: event.target.value }))}
                  placeholder="Support, Analytics"
                />
              </label>
              <div className="data-assets-form-wide data-assets-catalog-source-list">
                <div className="data-assets-section-header">
                  <div>
                    <span>Source object version IDs</span>
                    <p className="data-assets-helptext">Use the catalog browser below to pick a version. Selected versions become chips here.</p>
                  </div>
                  <SecondaryButton onClick={addSelectedSourceVersionToAsset} disabled={!sourceVersion?.id}>
                    Add selected version
                  </SecondaryButton>
                </div>
                <div className="data-assets-chip-list">
                  {assetSourceVersionIds.map((versionId) => (
                    <button
                      key={versionId}
                      type="button"
                      className="data-assets-chip"
                      onClick={() => removeAssetSourceVersionId(versionId)}
                      title="Remove source version"
                    >
                      <span>{versionId}</span>
                      <span aria-hidden="true">×</span>
                    </button>
                  ))}
                  {assetSourceVersionIds.length === 0 && (
                    <div className="data-assets-empty">No source versions selected yet. Use the catalog browser below to add them.</div>
                  )}
                </div>
                <div className="data-assets-actions">
                  <TertiaryButton onClick={() => setAssetForm((current) => ({ ...current, sourceObjectVersionIdsText: '' }))} disabled={assetSourceVersionIds.length === 0}>
                    Clear selected versions
                  </TertiaryButton>
                </div>
              </div>
            </div>
            <div className="data-assets-actions">
              <PrimaryButton onClick={() => (selectedAssetId ? void updateAsset() : void createAsset())} disabled={saving || !assetForm.id.trim() || !assetForm.name.trim()}>
                {selectedAssetId ? 'Save Asset' : 'Create Asset'}
              </PrimaryButton>
              <SecondaryButton onClick={() => void validateAsset()} disabled={saving || !selectedAssetId}>
                Validate
              </SecondaryButton>
              <SecondaryButton onClick={() => void downloadContract('yaml')} disabled={saving || !selectedAsset?.dataContractDownloadUrl}>
                Download YAML
              </SecondaryButton>
              <SecondaryButton onClick={() => void downloadContract('json')} disabled={saving || !selectedAsset?.dataContractDownloadUrl}>
                Download JSON
              </SecondaryButton>
              <SecondaryButton onClick={() => assetContractImportInputRef.current?.click()} disabled={saving || !selectedAssetId}>
                Import Contract
              </SecondaryButton>
              <SecondaryButton onClick={() => void deleteAsset()} disabled={saving || !selectedAssetId}>
                Delete
              </SecondaryButton>
              <input
                ref={assetContractImportInputRef}
                type="file"
                accept=".yaml,.yml,.json,application/x-yaml,application/json,text/yaml,text/json"
                onChange={(event) => void onAssetContractImportChange(event)}
                style={{ display: 'none' }}
              />
            </div>
          </section>

          <section className="data-assets-panel data-assets-panel-split">
            <div className="data-assets-section-header">
              <div>
                <h3>Contract Governance</h3>
                <span>Review the generated contract, change classification, and conformance status.</span>
              </div>
              <span>{loadingContractAnalysis ? 'Loading analysis…' : contractAnalysis ? `v${contractAnalysis.contract.version}` : 'No analysis loaded'}</span>
            </div>
            {contractAnalysis ? (
              <>
                <div className="data-assets-contract-summary">
                  <div className="data-assets-contract-card">
                    <span>Review status</span>
                    <strong>{contractAnalysis.latestContractVersion?.reviewStatus || 'pending'}</strong>
                    <small>{contractAnalysis.latestContractVersion?.reviewComments || 'No review comments yet.'}</small>
                  </div>
                  <div className="data-assets-contract-card">
                    <span>Change classification</span>
                    <strong>{contractAnalysis.comparison?.changeClassification || 'unknown'}</strong>
                    <small>
                      {contractAnalysis.comparison
                        ? `${contractAnalysis.comparison.summary.breakingChanges} breaking, ${contractAnalysis.comparison.summary.additiveChanges} additive, ${contractAnalysis.comparison.summary.compatibleChanges} compatible`
                        : 'No previous contract version to compare.'}
                    </small>
                  </div>
                  <div className="data-assets-contract-card">
                    <span>Conformance</span>
                    <strong>{contractAnalysis.conformance.ok ? 'pass' : 'fail'}</strong>
                    <small>
                      {contractAnalysis.conformance
                        ? `${contractAnalysis.conformance.summary.breakingIssues} breaking and ${contractAnalysis.conformance.summary.warningIssues} warning issue(s)`
                        : 'No conformance summary available.'}
                    </small>
                  </div>
                </div>

                <label className="data-assets-form-wide data-assets-contract-comments">

            <section className="data-assets-panel data-assets-panel-split">
              <div className="data-assets-section-header">
                <div>
                  <h3>Governance Discovery</h3>
                  <span>OpenMetadata-backed classifications and delivery evidence used to prioritize this asset.</span>
                </div>
                <span>{loadingGovernanceDiscovery ? 'Loading discovery…' : governanceDiscovery ? governanceDiscovery.priority : 'No discovery loaded'}</span>
              </div>
              {governanceDiscovery ? (
                <div className="data-assets-summary-card">
                  <div><strong>Priority:</strong> {governanceDiscovery.priority}</div>
                  <div><strong>Summary:</strong> {governanceDiscovery.summary || 'n/a'}</div>
                  <div><strong>Evidence classifications:</strong> {governanceDiscovery.evidenceClassifications.join(', ') || 'n/a'}</div>
                  <div><strong>Storage classifications:</strong> {governanceDiscovery.objectStorageClassifications.join(', ') || 'n/a'}</div>
                  <div><strong>Signals:</strong> {governanceDiscovery.signals.join(', ') || 'n/a'}</div>
                  <div><strong>Captured:</strong> {governanceDiscovery.capturedAt || 'n/a'}</div>
                  <div><strong>Snapshot:</strong> {governanceDiscovery.snapshotId || 'n/a'}</div>
                </div>
              ) : (
                <div className="data-assets-empty">Select a Data Asset to inspect governance discovery.</div>
              )}

              <div className="data-assets-section">
                <div className="data-assets-section-header">
                  <div>
                    <h3>Protection Advice</h3>
                    <span>Attribute-level masking and encryption guidance based on the selected version and current governance signals.</span>
                  </div>
                  <span>{loadingProtectionReview ? 'Loading protection details…' : protectionReviewSummary.advice}</span>
                </div>
                {selectedVersion ? (
                  loadingProtectionReview ? (
                    <div className="data-assets-empty">Loading source attribute protection details…</div>
                  ) : protectionReviewRows.length > 0 ? (
                    <>
                      <div className="data-assets-summary-card">
                        <div><strong>Advice:</strong> {protectionReviewSummary.advice}</div>
                        <div><strong>Sensitive attributes:</strong> {protectionReviewSummary.sensitiveCount}</div>
                        <div><strong>Protected:</strong> {protectionReviewSummary.protectedCount}</div>
                        <div><strong>Needs review:</strong> {protectionReviewSummary.unprotectedCount}</div>
                        <div><strong>Unavailable:</strong> {protectionReviewSummary.unavailableCount}</div>
                      </div>
                      <div className="data-assets-helptext">
                        Review the attributes below. When a field needs protection, open the protection editor to select a masking method or an encryption key.
                      </div>
                      {protectionReviewRows.map((row) => (
                        <div key={row.key} className="data-assets-summary-card">
                          <div><strong>Attribute:</strong> {row.attributeName}</div>
                          <div><strong>Version:</strong> {row.sourceDataObjectVersionId}</div>
                          <div><strong>Status:</strong> {row.statusDescription}</div>
                          <div><strong>Signals:</strong> {row.signals.join(', ') || 'n/a'}</div>
                          <div><strong>Recommendation:</strong> {row.recommendation}</div>
                          {row.target ? (
                            <TertiaryButton onClick={() => openDefinitionMappingTarget(row.target)}>
                              Open protection editor
                            </TertiaryButton>
                          ) : (
                            <div className="data-assets-helptext">This source version is not currently loaded in the catalog browser.</div>
                          )}
                        </div>
                      ))}
                    </>
                  ) : (
                    <div className="data-assets-empty">No source bindings are available for protection analysis.</div>
                  )
                ) : (
                  <div className="data-assets-empty">Select a version to inspect attribute-level protection advice.</div>
                )}
              </div>

            </section>

            <section className="data-assets-panel data-assets-panel-split">
              <div className="data-assets-section-header">
                <div>
                  <h3>Lineage and Impact</h3>
                  <span>Trace the selected asset back to catalog sources and forward to rules, monitors, and incidents.</span>
                </div>
                <span>{loadingLineage ? 'Loading lineage…' : lineage ? `${lineage.upstreamNodes.length} upstream · ${lineage.downstreamNodes.length} downstream` : 'No lineage loaded'}</span>
              </div>
              {lineage ? (
                <>
                  <div className="data-assets-summary-card">
                    <div><strong>Captured:</strong> {lineage.capturedAt || 'n/a'}</div>
                    <div><strong>Snapshot:</strong> {lineage.snapshotId || 'n/a'}</div>
                    <div><strong>Data product:</strong> {lineage.dataAsset.businessContext?.dataProductId || 'n/a'}</div>
                    <div><strong>Dataset:</strong> {lineage.dataAsset.businessContext?.datasetId || 'n/a'}</div>
                    <div><strong>Owner:</strong> {lineage.dataAsset.businessContext?.owner || 'n/a'}</div>
                    <div><strong>Domain:</strong> {lineage.dataAsset.businessContext?.domain || 'n/a'}</div>
                    <div><strong>Steward:</strong> {lineage.dataAsset.businessContext?.steward || 'n/a'}</div>
                    <div><strong>Criticality:</strong> {lineage.dataAsset.businessContext?.criticality || 'n/a'}</div>
                    <div><strong>Tags:</strong> {(lineage.dataAsset.businessContext?.tags || []).join(', ') || 'n/a'}</div>
                    <div><strong>Business definitions:</strong> {(lineage.dataAsset.businessContext?.businessDefinitions || []).join(', ') || 'n/a'}</div>
                    <div><strong>Lineage references:</strong> {(lineage.dataAsset.businessContext?.lineageReferences || []).join(', ') || 'n/a'}</div>
                    <div><strong>Consumers:</strong> {(lineage.dataAsset.businessContext?.consumers || []).join(', ') || 'n/a'}</div>
                  </div>

                  <div className="data-assets-summary-card">
                    <div><strong>Overlay summary:</strong> {lineage.businessContextOverlay?.summary || 'n/a'}</div>
                    <div><strong>Classification:</strong> {lineage.classificationView?.classification || 'public'}</div>
                    <div><strong>Rationale:</strong> {lineage.classificationView?.rationale || 'n/a'}</div>
                    <div><strong>Signals:</strong> {(lineage.classificationView?.signals || []).join(', ') || 'n/a'}</div>
                  </div>

                  {lineage.anomalyAnnotations.length > 0 && (
                    <div className="data-assets-summary-card">
                      <div className="data-assets-section-header">
                        <h3>Anomaly annotations</h3>
                        <span>{lineage.anomalyAnnotations.length}</span>
                      </div>
                      <ul className="data-assets-list-inline">
                        {lineage.anomalyAnnotations.map((annotation) => (
                          <li key={`${annotation.kind}-${annotation.summary}`}>
                            <strong>{annotation.kind}</strong>: {annotation.summary} ({annotation.severity}, {annotation.source})
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="data-assets-contract-columns">
                    <div className="data-assets-contract-list-card">
                      <div className="data-assets-section-header">
                        <h3>Upstream</h3>
                        <span>{lineage.upstreamNodes.length}</span>
                      </div>
                      <div className="data-assets-contract-list">
                        {groupLineageNodes(lineage.upstreamNodes).flat().length > 0 ? (
                          groupLineageNodes(lineage.upstreamNodes).map((group) => (
                            <div key={`upstream-${group[0]?.kind}`} className="data-assets-row-card">
                              <div className="data-assets-section-header">
                                <h3>{lineageKindLabel(group[0]?.kind || '')}</h3>
                                <span>{group.length}</span>
                              </div>
                              <div className="data-assets-contract-list">
                                {group.map((node) => (
                                  <div key={`${node.kind}-${node.id}`} className="data-assets-contract-item">
                                    <div>
                                      <strong>{node.name}</strong>
                                      <span>{node.detail || lineageKindLabel(node.kind)}</span>
                                    </div>
                                    {node.navigationTarget && onNavigate && (
                                      <TertiaryButton onClick={() => onNavigate(node.navigationTarget || '')}>
                                        Open
                                      </TertiaryButton>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))
                        ) : (
                          <div className="data-assets-empty">No upstream catalog links were resolved for this asset.</div>
                        )}
                      </div>
                    </div>

                    <div className="data-assets-contract-list-card">
                      <div className="data-assets-section-header">
                        <h3>Downstream</h3>
                        <span>{lineage.downstreamNodes.length}</span>
                      </div>
                      <div className="data-assets-contract-list">
                        {groupLineageNodes(lineage.downstreamNodes).flat().length > 0 ? (
                          groupLineageNodes(lineage.downstreamNodes).map((group) => (
                            <div key={`downstream-${group[0]?.kind}`} className="data-assets-row-card">
                              <div className="data-assets-section-header">
                                <h3>{lineageKindLabel(group[0]?.kind || '')}</h3>
                                <span>{group.length}</span>
                              </div>
                              <div className="data-assets-contract-list">
                                {group.map((node) => (
                                  <div key={`${node.kind}-${node.id}`} className="data-assets-contract-item">
                                    <div>
                                      <strong>{node.name}</strong>
                                      <span>{node.detail || lineageKindLabel(node.kind)}</span>
                                    </div>
                                    {node.navigationTarget && onNavigate && (
                                      <TertiaryButton onClick={() => onNavigate(node.navigationTarget || '')}>
                                        Open
                                      </TertiaryButton>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))
                        ) : (
                          <div className="data-assets-empty">No downstream rules, monitors, or incidents were resolved for this asset.</div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="data-assets-summary-card">
                    <div><strong>Contract changes:</strong> {lineage.impactSummary.contractChangeCount}</div>
                    <div><strong>Rules:</strong> {lineage.impactSummary.impactedRuleIds.length}</div>
                    <div><strong>Monitors:</strong> {lineage.impactSummary.impactedMonitorScopeIds.length}</div>
                    <div><strong>Incidents:</strong> {lineage.impactSummary.impactedIncidentIds.length}</div>
                    {lineage.impactSummary.notes.length > 0 && (
                      <ul className="data-assets-list-inline">
                        {lineage.impactSummary.notes.map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </>
              ) : (
                <div className="data-assets-empty">Select a Data Asset to inspect lineage and impact.</div>
              )}
            </section>
                  <span>Review comments</span>
                  <textarea
                    value={reviewComments}
                    onChange={(event) => setReviewComments(event.target.value)}
                    placeholder="Optional notes about the contract review"
                    rows={3}
                    disabled={saving}
                  />
                </label>

                {contractAnalysis.latestContractVersion?.reviewComments && (
                  <DiscussionPanel
                    title="Review discussion"
                    subtitle="Saved review note for the latest contract version."
                    entries={normalizeDiscussionEntries([
                      {
                        id: `review-${contractAnalysis.latestContractVersion.id || contractAnalysis.contract.id || 'current'}`,
                        authorName: 'Current reviewer',
                        content: contractAnalysis.latestContractVersion.reviewComments,
                        type: 'note',
                        createdAt: contractAnalysis.latestContractVersion.updatedAt || contractAnalysis.latestContractVersion.createdAt || new Date().toISOString(),
                      },
                    ], 'Current reviewer')}
                    emptyState="No review comments yet."
                  />
                )}

                <div className="data-assets-actions">
                  <SecondaryButton onClick={() => void loadContractAnalysis(selectedAssetId || '')} disabled={saving || loadingContractAnalysis || !selectedAssetId}>
                    Refresh Analysis
                  </SecondaryButton>
                  <PrimaryButton onClick={() => void reviewContract('approved')} disabled={saving || !selectedAssetId}>
                    Approve Contract
                  </PrimaryButton>
                  <SecondaryButton onClick={() => void reviewContract('rejected')} disabled={saving || !selectedAssetId}>
                    Reject Contract
                  </SecondaryButton>
                </div>

                <div className="data-assets-contract-columns">
                  <div className="data-assets-contract-list-card">
                    <div className="data-assets-section-header">
                      <h3>Breaking Changes</h3>
                      <span>{contractBreakingChanges.length}</span>
                    </div>
                    <div className="data-assets-contract-list">
                      {contractBreakingChanges.map((change) => (
                        <div key={`${change.fieldName}-${change.changeType}-${change.message}`} className="data-assets-contract-item is-breaking">
                          <strong>{change.fieldName}</strong>
                          <span>{change.message}</span>
                        </div>
                      ))}
                      {contractBreakingChanges.length === 0 && (
                        <div className="data-assets-empty">No breaking changes detected.</div>
                      )}
                    </div>
                  </div>

                  <div className="data-assets-contract-list-card">
                    <div className="data-assets-section-header">
                      <h3>Conformance Issues</h3>
                      <span>{contractAnalysis.conformance.summary.totalIssues}</span>
                    </div>
                    <div className="data-assets-contract-list">
                      {conformanceIssues.map((issue) => (
                        <div key={`${issue.fieldName}-${issue.issueType}-${issue.message}`} className={`data-assets-contract-item ${issue.severity === 'breaking' ? 'is-breaking' : 'is-warning'}`}>
                          <strong>{issue.fieldName}</strong>
                          <span>{issue.message}</span>
                        </div>
                      ))}
                      {conformanceIssues.length === 0 && (
                        <div className="data-assets-empty">The observed schema matches the current contract.</div>
                      )}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="data-assets-empty">Select a Data Asset to load the contract review summary.</div>
            )}
          </section>

          <section className="data-assets-panel">
            <div className="data-assets-panel-header">
              <h2>Version Editor</h2>
              <span>{loadingVersions ? 'Loading versions…' : `${versions.length} version(s)`}</span>
            </div>
            <div className="data-assets-version-picker">
              {versions.map((version) => (
                <button
                  key={version.id}
                  type="button"
                  className={`data-assets-version-pill ${version.id === selectedVersionId ? 'is-selected' : ''}`}
                  onClick={() => {
                    setSelectedVersionId(version.id)
                    setVersionForm(toVersionFormState(version))
                  }}
                >
                  v{version.version} · {version.id}
                </button>
              ))}
              {versions.length === 0 && <div className="data-assets-empty">No versions yet for this asset.</div>}
            </div>
            <div className="data-assets-form-grid">
              <label>
                <span>Version ID</span>
                <input
                  value={versionForm.id}
                  onChange={(event) => updateSelectedVersion({ id: event.target.value })}
                  placeholder="customer-health-v1"
                />
              </label>
              <label>
                <span>Version Number</span>
                <input
                  type="number"
                  min="1"
                  value={versionForm.version}
                  onChange={(event) => updateSelectedVersion({ version: event.target.value })}
                />
              </label>
              <label>
                <span>Created At</span>
                <input
                  value={versionForm.createdAt}
                  onChange={(event) => updateSelectedVersion({ createdAt: event.target.value })}
                  placeholder="2026-05-21T12:00:00Z"
                />
              </label>
              <label className="data-assets-form-wide">
                <span>Sample count for preview</span>
                <input
                  type="number"
                  min="1"
                  max="1000"
                  value={sampleCount}
                  onChange={(event) => setSampleCount(event.target.value)}
                />
              </label>
            </div>

            <div className="data-assets-section">
              <div className="data-assets-section-header">
                <h3>Source Selection</h3>
                <span>Pick a catalog source and lock the field type to the source schema.</span>
              </div>
              <div className="data-assets-form-grid data-assets-form-grid-compact">
                <label>
                  <span>Data Product</span>
                  <select
                    value={sourceProductId}
                    onChange={(event) => {
                      setSourceProductId(event.target.value)
                      setSourceDatasetId('')
                      setSourceObjectId('')
                      setSourceVersionId('')
                      setSourceAttributeId('')
                    }}
                  >
                    {filteredProducts.length === 0 && <option value="">No products available</option>}
                    {filteredProducts.map((product) => (
                      <option key={product.id} value={product.id}>{product.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Dataset</span>
                  <select
                    value={sourceDatasetId}
                    onChange={(event) => {
                      setSourceDatasetId(event.target.value)
                      setSourceObjectId('')
                      setSourceVersionId('')
                      setSourceAttributeId('')
                    }}
                  >
                    {sourceDatasetOptions.length === 0 && <option value="">{isLoadingDatasets(sourceProductId) ? 'Loading datasets…' : 'No datasets available'}</option>}
                    {sourceDatasetOptions.map((dataset) => (
                      <option key={dataset.id} value={dataset.id}>{dataset.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Data Object</span>
                  <select
                    value={sourceObjectId}
                    onChange={(event) => {
                      setSourceObjectId(event.target.value)
                      setSourceVersionId('')
                      setSourceAttributeId('')
                    }}
                  >
                    {sourceObjectOptions.length === 0 && <option value="">{isLoadingObjects(sourceDatasetId) ? 'Loading data objects…' : 'No data objects available'}</option>}
                    {sourceObjectOptions.map((dataObject) => (
                      <option key={dataObject.id} value={dataObject.id}>{dataObject.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Version</span>
                  <select
                    value={sourceVersionId}
                    onChange={(event) => {
                      setSourceVersionId(event.target.value)
                      setSourceAttributeId('')
                    }}
                  >
                    {sourceVersionOptions.length === 0 && <option value="">{isLoadingVersions(sourceObjectId) ? 'Loading versions…' : 'No versions available'}</option>}
                    {sourceVersionOptions.map((version) => (
                      <option key={version.id} value={version.id}>v{version.version}</option>
                    ))}
                  </select>
                </label>
                <label className="data-assets-form-wide">
                  <span>Source field</span>
                  <select
                    value={sourceAttributeId}
                    onChange={(event) => setSourceAttributeId(event.target.value)}
                  >
                    {sourceAttributeOptions.length === 0 && <option value="">{isLoadingAttributes(sourceVersionId) ? 'Loading fields…' : 'No fields available'}</option>}
                    {sourceAttributeOptions.map((attribute) => (
                      <option key={attribute.id} value={attribute.id}>{attribute.name} ({attribute.type})</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="data-assets-actions">
                <SecondaryButton onClick={() => addSourceBindingFromSelection()} disabled={!sourceVersion || !sourceAttribute}>
                  Add selected source field
                </SecondaryButton>
              </div>
              <div className="data-assets-summary-card">
                <div><strong>Selected source:</strong> {sourceSelectionSummary}</div>
                <div><strong>Schema mode:</strong> {sourceAttribute ? 'Locked to catalog metadata' : 'Select a field to lock the binding'}</div>
              </div>
            </div>

            <div className="data-assets-section">
              <div className="data-assets-section-header">
                <h3>Source Bindings</h3>
                <SecondaryButton onClick={() => updateSelectedVersion({ sourceBindings: [...versionForm.sourceBindings, newBinding()] })}>
                  Add Binding
                </SecondaryButton>
              </div>
              <div className="data-assets-stack">
                {versionForm.sourceBindings.map((binding, index) => (
                  <div key={`${binding.sourceFieldId}-${index}`} className="data-assets-row-card">
                    <div className="data-assets-form-grid data-assets-form-grid-compact">
                      <label>
                        <span>Source version</span>
                        <input
                          value={binding.sourceDataObjectVersionId}
                          readOnly={Boolean(binding.schemaLocked)}
                          onChange={(event) => {
                            if (binding.schemaLocked) return
                            const next = [...versionForm.sourceBindings]
                            next[index] = { ...binding, sourceDataObjectVersionId: event.target.value }
                            updateSelectedVersion({ sourceBindings: next })
                          }}
                          placeholder="dov-1"
                        />
                      </label>
                      <label>
                        <span>Field ID</span>
                        <input
                          value={binding.sourceFieldId}
                          readOnly={Boolean(binding.schemaLocked)}
                          onChange={(event) => {
                            if (binding.schemaLocked) return
                            const next = [...versionForm.sourceBindings]
                            next[index] = { ...binding, sourceFieldId: event.target.value }
                            updateSelectedVersion({ sourceBindings: next })
                          }}
                          placeholder="customer_id"
                        />
                      </label>
                      <label>
                        <span>Field name</span>
                        <input
                          value={binding.sourceFieldName}
                          readOnly={Boolean(binding.schemaLocked)}
                          onChange={(event) => {
                            if (binding.schemaLocked) return
                            const next = [...versionForm.sourceBindings]
                            next[index] = { ...binding, sourceFieldName: event.target.value }
                            updateSelectedVersion({ sourceBindings: next })
                          }}
                          placeholder="Customer ID"
                        />
                      </label>
                      <label>
                        <span>Field type</span>
                        <input
                          value={binding.sourceFieldType}
                          readOnly={Boolean(binding.schemaLocked)}
                          onChange={(event) => {
                            if (binding.schemaLocked) return
                            const next = [...versionForm.sourceBindings]
                            next[index] = { ...binding, sourceFieldType: event.target.value }
                            updateSelectedVersion({ sourceBindings: next })
                          }}
                          placeholder="string"
                        />
                      </label>
                      <label className="data-assets-check">
                        <span>Nullable</span>
                        <input
                          type="checkbox"
                          checked={binding.nullable}
                          onChange={(event) => {
                            const next = [...versionForm.sourceBindings]
                            next[index] = { ...binding, nullable: event.target.checked }
                            updateSelectedVersion({ sourceBindings: next })
                          }}
                        />
                      </label>
                    </div>
                    <div className="data-assets-row-actions">
                      <TertiaryButton
                        onClick={() => {
                          updateSelectedVersion({ sourceBindings: versionForm.sourceBindings.filter((_, currentIndex) => currentIndex !== index) })
                        }}
                      >
                        Remove
                      </TertiaryButton>
                    </div>
                  </div>
                ))}
                {versionForm.sourceBindings.length === 0 && <div className="data-assets-empty">No source bindings added yet.</div>}
              </div>
            </div>

            <div className="data-assets-section">
              <div className="data-assets-section-header">
                <h3>Filters</h3>
                <SecondaryButton onClick={() => updateSelectedVersion({ filters: [...versionForm.filters, newFilter()] })}>
                  Add Filter
                </SecondaryButton>
              </div>
              <div className="data-assets-stack">
                {versionForm.filters.map((filter, index) => (
                  <div key={`${filter.expression}-${index}`} className="data-assets-row-card">
                    <div className="data-assets-form-grid data-assets-form-grid-compact">
                      <label className="data-assets-form-wide">
                        <span>Expression</span>
                        <input
                          value={filter.expression}
                          onChange={(event) => {
                            const next = [...versionForm.filters]
                            next[index] = { ...filter, expression: event.target.value }
                            updateSelectedVersion({ filters: next })
                          }}
                          placeholder="amount > 0"
                        />
                      </label>
                      <label className="data-assets-form-wide">
                        <span>Description</span>
                        <input
                          value={filter.description || ''}
                          onChange={(event) => {
                            const next = [...versionForm.filters]
                            next[index] = { ...filter, description: event.target.value }
                            updateSelectedVersion({ filters: next })
                          }}
                          placeholder="Optional filter note"
                        />
                      </label>
                      <label className="data-assets-check">
                        <span>Enabled</span>
                        <input
                          type="checkbox"
                          checked={filter.enabled}
                          onChange={(event) => {
                            const next = [...versionForm.filters]
                            next[index] = { ...filter, enabled: event.target.checked }
                            updateSelectedVersion({ filters: next })
                          }}
                        />
                      </label>
                    </div>
                    <div className="data-assets-row-actions">
                      <TertiaryButton
                        onClick={() => {
                          updateSelectedVersion({ filters: versionForm.filters.filter((_, currentIndex) => currentIndex !== index) })
                        }}
                      >
                        Remove
                      </TertiaryButton>
                    </div>
                  </div>
                ))}
                {versionForm.filters.length === 0 && <div className="data-assets-empty">No filters added yet.</div>}
              </div>
            </div>

            <div className="data-assets-section">
              <div className="data-assets-section-header">
                <h3>Derived Fields</h3>
                <SecondaryButton onClick={() => updateSelectedVersion({ derivedFields: [...versionForm.derivedFields, newDerivedField()] })}>
                  Add Field
                </SecondaryButton>
              </div>
              <div className="data-assets-stack">
                {versionForm.derivedFields.map((field, index) => (
                  <div key={`${field.name}-${index}`} className="data-assets-row-card">
                    <div className="data-assets-form-grid data-assets-form-grid-compact">
                      <label>
                        <span>Name</span>
                        <input
                          value={field.name}
                          onChange={(event) => {
                            const next = [...versionForm.derivedFields]
                            next[index] = { ...field, name: event.target.value }
                            updateSelectedVersion({ derivedFields: next })
                          }}
                          placeholder="customer_segment"
                        />
                      </label>
                      <label>
                        <span>Type</span>
                        <input
                          value={field.dataType || ''}
                          onChange={(event) => {
                            const next = [...versionForm.derivedFields]
                            next[index] = { ...field, dataType: event.target.value }
                            updateSelectedVersion({ derivedFields: next })
                          }}
                          placeholder="string"
                        />
                      </label>
                      <label className="data-assets-form-wide">
                        <span>Expression</span>
                        <input
                          value={field.expression}
                          onChange={(event) => {
                            const next = [...versionForm.derivedFields]
                            next[index] = { ...field, expression: event.target.value }
                            updateSelectedVersion({ derivedFields: next })
                          }}
                          placeholder="case when amount > 100 then 'gold' end"
                        />
                      </label>
                      <label className="data-assets-form-wide">
                        <span>Source field IDs</span>
                        <input
                          value={field.sourceFieldIds.join(', ')}
                          onChange={(event) => {
                            const next = [...versionForm.derivedFields]
                            next[index] = { ...field, sourceFieldIds: normalizeList(event.target.value) }
                            updateSelectedVersion({ derivedFields: next })
                          }}
                          placeholder="field-1, field-2"
                        />
                      </label>
                    </div>
                    <div className="data-assets-row-actions">
                      <TertiaryButton
                        onClick={() => {
                          updateSelectedVersion({ derivedFields: versionForm.derivedFields.filter((_, currentIndex) => currentIndex !== index) })
                        }}
                      >
                        Remove
                      </TertiaryButton>
                    </div>
                  </div>
                ))}
                {versionForm.derivedFields.length === 0 && <div className="data-assets-empty">No derived fields added yet.</div>}
              </div>
            </div>

            <div className="data-assets-section">
              <div className="data-assets-section-header">
                <h3>Upload Preview</h3>
                <SecondaryButton onClick={() => updateSelectedVersion({ uploadPreview: { ...versionForm.uploadPreview, columns: [...versionForm.uploadPreview.columns, newPreviewColumn()] } })}>
                  Add Column
                </SecondaryButton>
              </div>
              <div className="data-assets-form-grid">
                <label className="data-assets-form-wide">
                  <span>Upload structure file</span>
                  <input
                    type="file"
                    accept=".csv,.tsv,.json,.xlsx,.xls,application/json,text/csv,text/tab-separated-values,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      event.target.value = ''
                      if (file) {
                        void importUploadPreview(file)
                      }
                    }}
                    disabled={uploadPreviewLoading || saving}
                  />
                </label>
                <label>
                  <span>File name</span>
                  <input
                    value={versionForm.uploadPreview.fileName || ''}
                    onChange={(event) => updateSelectedVersion({ uploadPreview: { ...versionForm.uploadPreview, fileName: event.target.value } })}
                    placeholder="customer_health.csv"
                  />
                </label>
                <label>
                  <span>File format</span>
                  <input
                    value={versionForm.uploadPreview.fileFormat || ''}
                    onChange={(event) => updateSelectedVersion({ uploadPreview: { ...versionForm.uploadPreview, fileFormat: event.target.value } })}
                    placeholder="csv"
                  />
                </label>
                <label className="data-assets-form-wide">
                  <span>Source URI</span>
                  <input
                    value={versionForm.uploadPreview.sourceUri || ''}
                    onChange={(event) => updateSelectedVersion({ uploadPreview: { ...versionForm.uploadPreview, sourceUri: event.target.value } })}
                    placeholder="s3a://dq-assets/customer-health.csv"
                  />
                </label>
                <div className="data-assets-form-wide data-assets-helptext">
                  Upload a CSV, TSV, XLSX, plain JSON file, or a JSON Schema file. Imported types are inferred when possible; edit any column type manually when the source does not expose it clearly.
                </div>
              </div>
              <div className="data-assets-stack">
                {versionForm.uploadPreview.columns.map((column, index) => (
                  <div key={`${column.name}-${index}`} className="data-assets-row-card">
                    <div className="data-assets-form-grid data-assets-form-grid-compact">
                      <label>
                        <span>Column name</span>
                        <input
                          value={column.name}
                          onChange={(event) => {
                            const nextColumns = [...versionForm.uploadPreview.columns]
                            nextColumns[index] = { ...column, name: event.target.value }
                            updateSelectedVersion({ uploadPreview: { ...versionForm.uploadPreview, columns: nextColumns } })
                          }}
                          placeholder="customer_id"
                        />
                      </label>
                      <label>
                        <span>Type</span>
                        <input
                          value={column.dataType}
                          onChange={(event) => {
                            const nextColumns = [...versionForm.uploadPreview.columns]
                            nextColumns[index] = { ...column, dataType: event.target.value }
                            updateSelectedVersion({ uploadPreview: { ...versionForm.uploadPreview, columns: nextColumns } })
                          }}
                          placeholder="string"
                        />
                      </label>
                      <label className="data-assets-check">
                        <span>Nullable</span>
                        <input
                          type="checkbox"
                          checked={column.nullable}
                          onChange={(event) => {
                            const nextColumns = [...versionForm.uploadPreview.columns]
                            nextColumns[index] = { ...column, nullable: event.target.checked }
                            updateSelectedVersion({ uploadPreview: { ...versionForm.uploadPreview, columns: nextColumns } })
                          }}
                        />
                      </label>
                    </div>
                    <div className="data-assets-row-actions">
                      <TertiaryButton
                        onClick={() => {
                          updateSelectedVersion({
                            uploadPreview: {
                              ...versionForm.uploadPreview,
                              columns: versionForm.uploadPreview.columns.filter((_, currentIndex) => currentIndex !== index),
                            },
                          })
                        }}
                      >
                        Remove
                      </TertiaryButton>
                    </div>
                  </div>
                ))}
                {versionForm.uploadPreview.columns.length === 0 && <div className="data-assets-empty">No schema preview columns added yet.</div>}
              </div>
            </div>

            <div className="data-assets-actions">
              <PrimaryButton onClick={() => void createVersion()} disabled={saving || !selectedAssetId || !versionForm.id.trim()}>
                Save Version
              </PrimaryButton>
              <SecondaryButton onClick={() => void generateTestData()} disabled={saving || !selectedAssetId}>
                Generate Test Data
              </SecondaryButton>
            </div>
          </section>

          <section className="data-assets-panel data-assets-panel-split">
            <div className="data-assets-panel-header">
              <h2>Resolved State</h2>
              <span>Current version and validation feedback</span>
            </div>
            <div className="data-assets-split-grid">
              <div>
                <h3>Selected Version</h3>
                {selectedVersion ? (
                  <div className="data-assets-summary-card">
                    <div><strong>ID:</strong> {selectedVersion.id}</div>
                    <div><strong>Version:</strong> v{selectedVersion.version}</div>
                    <div><strong>Created:</strong> {selectedVersion.createdAt || 'n/a'}</div>
                    <div><strong>Bindings:</strong> {selectedVersion.sourceBindings.length}</div>
                    <div><strong>Derived fields:</strong> {selectedVersion.derivedFields.length}</div>
                    <div><strong>Filters:</strong> {selectedVersion.filters.length}</div>
                  </div>
                ) : (
                  <div className="data-assets-empty">No version selected.</div>
                )}
              </div>
              <div>
                <h3>Validation</h3>
                {validationResult ? (
                  <div className="data-assets-summary-card">
                    <div><strong>Status:</strong> {validationResult.ok ? 'OK' : 'Issues found'}</div>
                    <div><strong>Version:</strong> {validationResult.version.id}</div>
                    <div><strong>Issues:</strong> {validationResult.issues.length}</div>
                    {validationResult.issues.length > 0 && (
                      <ul className="data-assets-list-inline">
                        {validationResult.issues.map((issue) => (
                          <li key={issue}>{issue}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : (
                  <div className="data-assets-empty">Run validation to inspect the resolved asset state.</div>
                )}
              </div>
            </div>
            <div className="data-assets-section">
              <h3>Generated Payload</h3>
              {generatedPayload ? (
                <pre className="data-assets-json">{JSON.stringify(generatedPayload, null, 2)}</pre>
              ) : (
                <div className="data-assets-empty">Generate test data to inspect the resolved request payload.</div>
              )}
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}

const toVersionFormState = (version: DataAssetVersion): VersionFormState => ({
  id: version.id,
  version: String(version.version),
  createdAt: version.createdAt,
  sourceBindings: version.sourceBindings.map((binding) => ({
    sourceDataObjectVersionId: binding.sourceDataObjectVersionId,
    sourceFieldId: binding.sourceFieldId,
    sourceFieldName: binding.sourceFieldName,
    sourceFieldType: binding.sourceFieldType,
    nullable: Boolean(binding.nullable),
  })),
  filters: version.filters.map((filter) => ({
    expression: filter.expression,
    enabled: Boolean(filter.enabled),
    description: filter.description,
  })),
  derivedFields: version.derivedFields.map((field) => ({
    name: field.name,
    expression: field.expression,
    dataType: field.dataType,
    nullable: field.nullable,
    sourceFieldIds: field.sourceFieldIds || [],
  })),
  uploadPreview: {
    fileName: version.uploadPreview?.fileName || '',
    fileFormat: version.uploadPreview?.fileFormat || '',
    sourceUri: version.uploadPreview?.sourceUri || '',
    columns: (version.uploadPreview?.columns || []).map((column) => ({
      name: column.name,
      dataType: column.dataType,
      nullable: Boolean(column.nullable),
    })),
  },
})
