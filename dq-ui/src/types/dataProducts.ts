/**
 * Data Product Browser Types
 * Hierarchical structure: Product -> Dataset -> DataObject -> Version -> Delivery -> Attributes
 */

export interface DataAttribute {
  id: string
  name: string
  type: 'string' | 'number' | 'boolean' | 'date' | 'timestamp' | 'decimal' | 'array' | 'object'
  nullable: boolean
  tags?: string[]
  description?: string
  format?: string // e.g., "email", "uuid", "date-time"
  isCde?: boolean // Critical Data Element indicator
  isPrimaryKey?: boolean // Primary Key indicator
  ruleCount?: number // Number of DQ rules associated with this attribute
  definitionId?: string
  definitionMappingStatus?: 'explicit' | 'inherited' | 'explicit_unmapped' | 'inherited_unmapped' | 'unmapped'
  definitionMappingAttributeId?: string
  definitionMappingVersionId?: string
  definitionMappingMappedBy?: string
  definitionMappingCreatedAt?: string
  maskingMethod?: string
  encryptionRequired?: boolean
  encryptionKeyId?: string
  protectionConfiguredBy?: string
  protectionUpdatedAt?: string
}

export interface DataObjectVersion {
  id: string
  dataObjectId: string
  version: number
  createdAt: string
  tags?: string[]
  attributes: DataAttribute[]
  description?: string
  schemaHash: string // Hash of schema for change detection
  deliveries?: DataDelivery[]
}

export interface DataObject {
  id: string
  dataSetId: string
  name: string
  tags?: string[]
  description?: string
  icon: string
  createdAt: string
  latestVersionId: string
  versions: DataObjectVersion[]
}

export interface DataDelivery {
  id: string
  versionId: string
  recordCount: number
  sizeBytes: number // in bytes
  status: 'completed' | 'failed' | 'in-progress'
  deliveredAt: string
  filePath?: string
}

export interface DataSet {
  id: string
  productId?: string // Optional for standalone datasets
  name: string
  tags?: string[]
  description?: string
  owner?: string
  createdAt: string
  workspaceId?: string
  dataContractDownloadUrl?: string
  dataObjects: DataObject[]
}

export interface DataProduct {
  id: string
  name: string
  tags?: string[]
  description?: string
  owner?: string
  createdAt: string
  icon: string
  workspaceId?: string
  datasets?: DataSet[]
}

export interface CatalogItem {
  type: 'product' | 'dataset'
  product?: DataProduct
  dataset?: DataSet
}

export interface DataProductBrowserState {
  selectedProduct: DataProduct | null
  selectedDataset: DataSet | null
  selectedDataObject: DataObject | null
  selectedVersion: DataObjectVersion | null
  selectedDelivery: DataDelivery | null
  searchQuery: string
}

export interface ApplicableRule {
  ruleId: string
  ruleName: string
  targetAttributes: string[] // Attribute IDs this rule applies to
  status: 'active' | 'draft' | 'testing'
}

export interface DefinitionMappingTarget {
  productId?: string
  datasetId: string
  objectId: string
  versionId: string
  attributeId?: string
}
