import React, { createContext, useState, useCallback, ReactNode, useEffect, useContext } from 'react'

// Unwrap paginated { data: [] } envelope or pass through raw arrays
const unwrapPage = (r: any): any[] => Array.isArray(r?.data) ? r.data : (Array.isArray(r) ? r : [])
const normalizeTags = (values: unknown): string[] => {
  if (!Array.isArray(values)) {
    return []
  }

  const seen = new Set<string>()
  const tags: string[] = []

  for (const value of values) {
    const tag = String(value || '').trim()
    const key = tag.toLowerCase()
    if (!tag || seen.has(key)) {
      continue
    }
    seen.add(key)
    tags.push(tag)
  }

  return tags
}
import {
  DataProduct,
  DataSet,
  DataObject,
  DataObjectVersion,
  DataDelivery,
  DataProductBrowserState,
  DataAttribute,
} from '../types/dataProducts'
import { usePerformanceMonitoringContext } from './PerformanceMonitoringContext'
import { SettingsContext } from './SettingsContext'
import { AuthContext, clearPersistedAuthSession, getAuthToken } from './AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { matchesTokenizedSearch } from '../utils/listFilterState'

interface DataProductContextType {
  state: DataProductBrowserState
  selectProduct: (product: DataProduct | null) => void
  selectDataset: (dataset: DataSet | null) => void
  selectDataObject: (dataObject: DataObject | null) => void
  selectVersion: (version: DataObjectVersion | null) => void
  selectDelivery: (delivery: DataDelivery | null) => void
  setSearchQuery: (query: string) => void
  reset: () => void
  filteredProducts: DataProduct[]
  allProducts: DataProduct[]
  isLoadingProducts: boolean
  standaloneDatasets: DataSet[]
  searchResults: (products: DataProduct[], datasets: DataSet[]) => { products: DataProduct[]; datasets: DataSet[] }
  // Lazy loading methods
  loadDatasets: (productId: string) => Promise<void>
  loadDataObjects: (datasetId: string) => Promise<void>
  loadVersions: (objectId: string) => Promise<DataObjectVersion[] | null>
  loadAttributes: (versionId: string) => Promise<DataAttribute[] | null>
  isLoadingDatasets: (productId: string) => boolean
  isLoadingObjects: (datasetId: string) => boolean
  isLoadingVersions: (objectId: string) => boolean
  isLoadingAttributes: (versionId: string) => boolean
}

export const DataProductContext = createContext<DataProductContextType | undefined>(undefined)

export const DataProductProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { startTimer, endTimer, trackCache } = usePerformanceMonitoringContext()
  const settings = useContext(SettingsContext)
  const authContext = useContext(AuthContext)
  const apiBase = toApiGroupV1Base('data-catalog', settings?.applicationSettings?.apiBaseUrl)
  
  const [state, setState] = useState<DataProductBrowserState>({
    selectedProduct: null,
    selectedDataset: null,
    selectedDataObject: null,
    selectedVersion: null,
    selectedDelivery: null,
    searchQuery: '',
  })
  
  const [loadedProducts, setLoadedProducts] = useState<DataProduct[]>([])
  const [isLoading, setIsLoading] = useState(true)
  
  // Track what's currently being loaded to prevent duplicate requests
  const [loadingDatasets, setLoadingDatasets] = useState<Set<string>>(new Set())
  const [loadingObjects, setLoadingObjects] = useState<Set<string>>(new Set())
  const [loadingVersions, setLoadingVersions] = useState<Set<string>>(new Set())
  const [loadingAttributes, setLoadingAttributes] = useState<Set<string>>(new Set())
  
  // Track what's already been loaded to avoid refetching
  const [loadedDatasets, setLoadedDatasets] = useState<Set<string>>(new Set())
  const [loadedObjects, setLoadedObjects] = useState<Set<string>>(new Set())
  const [loadedVersions, setLoadedVersions] = useState<Set<string>>(new Set())
  const [loadedAttributesCache, setLoadedAttributesCache] = useState<Set<string>>(new Set())
  const [standaloneDatasets, setStandaloneDatasets] = useState<DataSet[]>([])
  
  const [ruleCounts, setRuleCounts] = useState<Record<string, number>>({})
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  const canUseAuthenticatedRequests = Boolean(authContext?.isAuthenticated || authToken)

  useEffect(() => {
    const syncTokenFromStorage = () => {
      setAuthToken(getAuthToken())
    }

    syncTokenFromStorage()
    if (typeof window !== 'undefined') {
      window.addEventListener('storage', syncTokenFromStorage)
      window.addEventListener('dq-auth-token-changed', syncTokenFromStorage)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', syncTokenFromStorage)
        window.removeEventListener('dq-auth-token-changed', syncTokenFromStorage)
      }
    }
  }, [])

  const getAuthHeaders = useCallback((): HeadersInit => {
    return authToken ? { Authorization: `Bearer ${authToken}` } : {}
  }, [authToken])

  const getAuthRequestInit = useCallback((): RequestInit => ({
    headers: getAuthHeaders(),
    credentials: 'include',
  }), [getAuthHeaders])

  // Load only products initially (lightweight)
  useEffect(() => {
    const fetchProducts = async () => {
      if (!canUseAuthenticatedRequests) {
        setLoadedProducts([])
        setRuleCounts({})
        setIsLoading(false)
        return
      }

      const timer = startTimer()
      try {
        const [productsRes, ruleCountsRes] = await Promise.all([
          fetch(`${apiBase}/data-products`, getAuthRequestInit()),
          fetch(`${apiBase}/attribute-rule-counts`, getAuthRequestInit()),
        ])

        if (!productsRes.ok) {
          if (productsRes.status === 401) {
            clearPersistedAuthSession(true)
            setAuthToken(null)
            setLoadedProducts([])
            setRuleCounts({})
            setIsLoading(false)
            endTimer('load-products', timer, false, { reason: 'Unauthorized' })
            return
          }
          console.error('Failed to fetch products from database', {
            status: productsRes.status,
            statusText: productsRes.statusText,
            url: productsRes.url,
          })
          setLoadedProducts([])
          setIsLoading(false)
          endTimer('load-products', timer, false, { reason: 'API failed' })
          return
        }

        const productsJson = await productsRes.json()
        console.debug(`[DataProductContext] Raw API response:`, {
          url: productsRes.url,
          status: productsRes.status,
          hasDataKey: 'data' in productsJson,
          dataLength: Array.isArray(productsJson?.data) ? productsJson.data.length : 'N/A',
          firstItemKeys: Array.isArray(productsJson?.data) ? Object.keys(productsJson.data[0] || {}) : [],
          firstItem: Array.isArray(productsJson?.data) ? productsJson.data[0] : null,
        })

        const products = unwrapPage(productsJson)
        const counts = ruleCountsRes.ok ? await ruleCountsRes.json() : {}
        
        setRuleCounts(counts)

        // Transform products with empty datasets arrays (to be loaded on-demand)
        const transformedProducts: DataProduct[] = products.map((product: any) => {
          // DEBUG: Log what workspace_id values we're receiving from API
          if (products.indexOf(product) < 2) {
            console.debug(`[DataProductContext] Product "${product.name}":`, {
              has_workspace_id_key: 'workspace_id' in product,
              workspace_id_value: product.workspace_id,
              workspace_id_type: typeof product.workspace_id,
              all_keys: Object.keys(product),
            })
          }
          return {
            id: product.id,
            name: product.name,
            tags: normalizeTags(product.tags || product.tag_ids),
            description: product.description || '',
            owner: product.owner || '',
            createdAt: product.created_at || '',
            icon: product.icon || 'table',
            workspaceId: product.workspace_id ?? 'default',
            datasets: [], // Load on-demand when product is expanded
          }
        })

        setLoadedProducts(transformedProducts)
        setIsLoading(false)
        endTimer('load-products', timer, true, { count: transformedProducts.length })
      } catch (error) {
        console.error('Error fetching products:', error)
        setLoadedProducts([])
        setIsLoading(false)
        endTimer('load-products', timer, false, { error: String(error) })
      }
    }

    fetchProducts()
  }, [apiBase, canUseAuthenticatedRequests, startTimer, endTimer, getAuthRequestInit])

  // Lazy load datasets for a product
  const loadDatasets = useCallback(async (productId: string) => {
    if (!canUseAuthenticatedRequests) {
      return
    }

    
    // Check if already loaded - but also verify the product actually has datasets
    if (loadedDatasets.has(productId)) {
      const product = loadedProducts.find(p => p.id === productId)
      const hasDatasets = product && product.datasets && product.datasets.length > 0
      if (hasDatasets) {
        trackCache('load-datasets', true)
        return
      } else {
        setLoadedDatasets(prev => {
          const next = new Set(prev)
          next.delete(productId)
          return next
        })
      }
    }
    
    if (loadingDatasets.has(productId)) {
      return
    }

    trackCache('load-datasets', false)
    setLoadingDatasets(prev => new Set(prev).add(productId))
    const timer = startTimer()

    try {
      const url = `${apiBase}/data-sets?productId=${productId}`
      const response = await fetch(url, getAuthRequestInit())
      if (!response.ok) throw new Error('Failed to fetch datasets')
      
      const sets = unwrapPage(await response.json())

      // DEBUG: Log datasets  workspace_id values
      console.debug(`[DataProductContext] Datasets for product ${productId}:`, sets.slice(0, 2).map(s => ({
        name: s.name,
        has_workspace_id: 'workspace_id' in s,
        workspace_id: s.workspace_id,
      })))

      // Update the product with its datasets
      setLoadedProducts(prev => {
        const updated = prev.map(product => {
          if (product.id !== productId) {
            return product
          }
          
          const updatedProduct = {
            ...product,
            datasets: sets.map((set: any) => ({
              id: set.id,
              productId: set.product_id,
              name: set.name,
              tags: normalizeTags(set.tags || set.tag_ids),
              description: set.description || '',
              owner: set.owner || '',
              createdAt: set.created_at || '',
              workspaceId: set.workspace_id ?? 'default',
              dataContractDownloadUrl: set.data_contract_download_url || '',
              dataObjects: [], // Load on-demand when dataset is expanded
            })),
          }
          return updatedProduct
        })
        return updated
      })

      setLoadedDatasets(prev => {
        const next = new Set(prev)
        next.add(productId)
        return next
      })
      endTimer('load-datasets', timer, true, { productId, count: sets.length })
    } catch (error) {
      endTimer('load-datasets', timer, false, { productId, error: String(error) })
    } finally {
      setLoadingDatasets(prev => {
        const next = new Set(prev)
        next.delete(productId)
        return next
      })
    }
  }, [loadedDatasets, loadingDatasets, apiBase, canUseAuthenticatedRequests, startTimer, endTimer, trackCache, loadedProducts, getAuthRequestInit])

  // Lazy load data objects for a dataset
  const loadDataObjects = useCallback(async (datasetId: string) => {
    if (!canUseAuthenticatedRequests) {
      return
    }

    
    // Check if already loaded - but also verify the dataset actually has data objects
    if (loadedObjects.has(datasetId)) {
      // Find the dataset in state to check if it has objects
      let hasObjects = false
      for (const product of loadedProducts) {
        const dataset = product.datasets?.find(ds => ds.id === datasetId)
        if (dataset && dataset.dataObjects && dataset.dataObjects.length > 0) {
          hasObjects = true
          break
        }
      }
      if (!hasObjects) {
        const standaloneDataset = standaloneDatasets.find(ds => ds.id === datasetId)
        if (standaloneDataset && standaloneDataset.dataObjects && standaloneDataset.dataObjects.length > 0) {
          hasObjects = true
        }
      }
      if (hasObjects) {
        trackCache('load-objects', true)
        return
      } else {
        setLoadedObjects(prev => {
          const next = new Set(prev)
          next.delete(datasetId)
          return next
        })
      }
    }
    
    if (loadingObjects.has(datasetId)) {
      return
    }

    trackCache('load-objects', false)
    setLoadingObjects(prev => new Set(prev).add(datasetId))
    const timer = startTimer()

    try {
      const url = `${apiBase}/data-objects-catalog?dataSetId=${datasetId}`
      const response = await fetch(url, getAuthRequestInit())
      if (!response.ok) throw new Error('Failed to fetch data objects')
      
      const objects = unwrapPage(await response.json())

      // Update the dataset with its data objects
      setLoadedProducts(prev => prev.map(product => ({
        ...product,
        datasets: product.datasets?.map(dataset => {
          if (dataset.id !== datasetId) return dataset
          
          const updatedDataset = {
            ...dataset,
            dataObjects: objects.map((obj: any) => ({
              id: obj.id,
              dataSetId: obj.dataset_id,
              name: obj.name,
              tags: normalizeTags(obj.tags || obj.tag_ids),
              description: obj.description || '',
              icon: obj.icon || 'database',
              createdAt: obj.created_at || '',
              latestVersionId: obj.latest_version_id || '',
              versions: [], // Load on-demand when object is expanded
            })),
          }
          return updatedDataset
        }),
      })))

      setStandaloneDatasets(prev => prev.map(dataset => {
        if (dataset.id !== datasetId) {
          return dataset
        }

        return {
          ...dataset,
          dataObjects: objects.map((obj: any) => ({
            id: obj.id,
            dataSetId: obj.dataset_id,
            name: obj.name,
            tags: normalizeTags(obj.tags || obj.tag_ids),
            description: obj.description || '',
            icon: obj.icon || 'database',
            createdAt: obj.created_at || '',
            latestVersionId: obj.latest_version_id || '',
            versions: [],
          })),
        }
      }))

      setLoadedObjects(prev => {
        const next = new Set(prev)
        next.add(datasetId)
        return next
      })
      endTimer('load-objects', timer, true, { datasetId, count: objects.length })
    } catch (error) {
      endTimer('load-objects', timer, false, { datasetId, error: String(error) })
    } finally {
      setLoadingObjects(prev => {
        const next = new Set(prev)
        next.delete(datasetId)
        return next
      })
    }
  }, [loadedObjects, loadingObjects, apiBase, canUseAuthenticatedRequests, startTimer, endTimer, trackCache, loadedProducts, standaloneDatasets, getAuthRequestInit])

  // Lazy load versions for a data object
  const loadVersions = useCallback(async (objectId: string) => {
    if (!canUseAuthenticatedRequests) {
      return null
    }

    
    // If already loading, wait for it to complete
    if (loadingVersions.has(objectId)) {
      return null
    }
    
    // If already loaded, return the cached versions - but verify they exist
    if (loadedVersions.has(objectId)) {
      trackCache('load-versions', true)
      // Find and return the cached versions from loadedProducts
      for (const product of loadedProducts) {
        for (const dataset of product.datasets || []) {
          const obj = dataset.dataObjects?.find(o => o.id === objectId)
          if (obj && obj.versions && obj.versions.length > 0) {
            return obj.versions
          }
        }
      }
      for (const dataset of standaloneDatasets) {
        const obj = dataset.dataObjects?.find(o => o.id === objectId)
        if (obj && obj.versions && obj.versions.length > 0) {
          return obj.versions
        }
      }
      setLoadedVersions(prev => {
        const next = new Set(prev)
        next.delete(objectId)
        return next
      })
    }

    trackCache('load-versions', false)
    setLoadingVersions(prev => new Set(prev).add(objectId))
    const timer = startTimer()

    try {
      const [versionsRes, deliveriesRes] = await Promise.all([
        fetch(`${apiBase}/data-object-versions?objectId=${objectId}`, getAuthRequestInit()),
        fetch(`${apiBase}/data-deliveries`, getAuthRequestInit()),
      ])
      
      if (!versionsRes.ok) throw new Error('Failed to fetch versions')
      
      const versions = unwrapPage(await versionsRes.json())
      const deliveries = deliveriesRes.ok ? unwrapPage(await deliveriesRes.json()) : []

      const objectVersions = versions.map((ver: any) => ({
        id: ver.id,
        dataObjectId: ver.data_object_id,
        version: ver.version,
        createdAt: ver.created_at || '',
        tags: normalizeTags(ver.tags || ver.tag_ids),
        schemaHash: ver.schema_hash || '',
        attributes: [], // Load on-demand when version is selected
        deliveries: deliveries
          .filter((del: any) => del.data_object_id === objectId && del.version === ver.version)
          .map((del: any) => ({
            id: del.id,
            versionId: ver.id,
            recordCount: del.record_count,
            sizeBytes: del.size_bytes,
            status: del.status,
            deliveredAt: del.timestamp,
            filePath: del.file_path || undefined,
          })),
      }))

      // Update the data object with its versions
      setLoadedProducts(prev => prev.map(product => ({
        ...product,
        datasets: product.datasets?.map(dataset => ({
          ...dataset,
          dataObjects: dataset.dataObjects?.map(obj => {
            if (obj.id !== objectId) return obj
            
            return {
              ...obj,
              latestVersionId: objectVersions.length > 0 ? objectVersions[objectVersions.length - 1].id : obj.latestVersionId,
              versions: objectVersions,
            }
          }),
        })),
      })))

      setStandaloneDatasets(prev => prev.map(dataset => ({
        ...dataset,
        dataObjects: dataset.dataObjects?.map(obj => {
          if (obj.id !== objectId) {
            return obj
          }

          return {
            ...obj,
            latestVersionId: objectVersions.length > 0 ? objectVersions[objectVersions.length - 1].id : obj.latestVersionId,
            versions: objectVersions,
          }
        }),
      })))

      setLoadedVersions(prev => {
        const next = new Set(prev)
        next.add(objectId)
        return next
      })
      endTimer('load-versions', timer, true, { objectId, count: objectVersions.length })
      
      // Return the loaded versions so caller can select one
      return objectVersions
    } catch (error) {
      console.error(`Error loading versions for object ${objectId}:`, error)
      endTimer('load-versions', timer, false, { objectId, error: String(error) })
      return null
    } finally {
      setLoadingVersions(prev => {
        const next = new Set(prev)
        next.delete(objectId)
        return next
      })
    }
  }, [loadedVersions, loadingVersions, apiBase, canUseAuthenticatedRequests, loadedProducts, standaloneDatasets, startTimer, endTimer, trackCache, getAuthRequestInit])

  // Lazy load attributes for a version
  const loadAttributes = useCallback(async (versionId: string): Promise<DataAttribute[] | null> => {
    if (!canUseAuthenticatedRequests) {
      return null
    }

    // If already cached, find and return the cached attributes
    if (loadedAttributesCache.has(versionId)) {
      trackCache('load-attributes', true)
      // Search for the version with attributes in loadedProducts
      for (const product of loadedProducts) {
        for (const dataset of product.datasets || []) {
          for (const obj of dataset.dataObjects || []) {
            const version = obj.versions?.find(v => v.id === versionId)
            if (version && version.attributes && version.attributes.length > 0) {
              return version.attributes
            }
          }
        }
      }
      for (const dataset of standaloneDatasets) {
        for (const obj of dataset.dataObjects || []) {
          const version = obj.versions?.find(v => v.id === versionId)
          if (version && version.attributes && version.attributes.length > 0) {
            return version.attributes
          }
        }
      }
      // If cache marked but attributes missing, clear it and reload
      setLoadedAttributesCache(prev => {
        const next = new Set(prev)
        next.delete(versionId)
        return next
      })
    }
    
    if (loadingAttributes.has(versionId)) {
      return null
    }

    trackCache('load-attributes', false)
    setLoadingAttributes(prev => new Set(prev).add(versionId))
    const timer = startTimer()

    try {
      const response = await fetch(`${apiBase}/attributes-catalog?versionId=${versionId}`, getAuthRequestInit())
      if (!response.ok) throw new Error('Failed to fetch attributes')
      
      const attributes = unwrapPage(await response.json())

      const mappedAttributes = attributes.map((attr: any) => ({
        id: attr.id,
        name: attr.name,
        type: attr.type,
        nullable: attr.nullable !== false,
        tags: normalizeTags(attr.tags || attr.tag_ids),
        format: attr.format || undefined,
        description: attr.description || undefined,
        isCde: attr.is_cde || false,
        isPrimaryKey: attr.is_primary_key || false,
        ruleCount: ruleCounts[attr.id] || 0,
        definitionId: attr.definition_id || undefined,
        definitionMappingStatus: attr.definition_mapping_status || 'unmapped',
        definitionMappingAttributeId: attr.definition_mapping_attribute_id || undefined,
        definitionMappingVersionId: attr.definition_mapping_version_id || undefined,
        definitionMappingMappedBy: attr.definition_mapping_mapped_by || undefined,
        definitionMappingCreatedAt: attr.definition_mapping_created_at || undefined,
      }))

      // Update the version with its attributes
      setLoadedProducts(prev => prev.map(product => ({
        ...product,
        datasets: product.datasets?.map(dataset => ({
          ...dataset,
          dataObjects: dataset.dataObjects?.map(obj => ({
            ...obj,
            versions: obj.versions?.map(ver => {
              if (ver.id !== versionId) return ver
              
              return {
                ...ver,
                attributes: mappedAttributes,
              }
            }),
          })),
        })),
      })))

      setStandaloneDatasets(prev => prev.map(dataset => ({
        ...dataset,
        dataObjects: dataset.dataObjects?.map(obj => ({
          ...obj,
          versions: obj.versions?.map(ver => {
            if (ver.id !== versionId) {
              return ver
            }

            return {
              ...ver,
              attributes: mappedAttributes,
            }
          }),
        })),
      })))

      setLoadedAttributesCache(prev => new Set(prev).add(versionId))
      endTimer('load-attributes', timer, true, { versionId, count: mappedAttributes.length })
      return mappedAttributes
    } catch (error) {
      console.error(`Error loading attributes for version ${versionId}:`, error)
      endTimer('load-attributes', timer, false, { versionId, error: String(error) })
      return null
    } finally {
      setLoadingAttributes(prev => {
        const next = new Set(prev)
        next.delete(versionId)
        return next
      })
    }
  }, [loadedAttributesCache, loadingAttributes, apiBase, canUseAuthenticatedRequests, ruleCounts, loadedProducts, standaloneDatasets, startTimer, endTimer, trackCache, getAuthRequestInit])

  const selectProduct = useCallback((product: DataProduct | null) => {
    setState(prev => ({
      ...prev,
      selectedProduct: product,
      selectedDataset: null,
      selectedDataObject: null,
      selectedVersion: null,
      selectedDelivery: null,
    }))
  }, [])

  const selectDataset = useCallback((dataset: DataSet | null) => {
    setState(prev => ({
      ...prev,
      selectedDataset: dataset,
      selectedDataObject: null,
      selectedVersion: null,
      selectedDelivery: null,
    }))
  }, [])

  const selectDataObject = useCallback((dataObject: DataObject | null) => {
    setState(prev => ({
      ...prev,
      selectedDataObject: dataObject,
      selectedVersion: null, // Don't auto-select version here - versions are lazy loaded
      selectedDelivery: null,
    }))
  }, [])

  const selectVersion = useCallback((version: DataObjectVersion | null) => {
    setState(prev => ({
      ...prev,
      selectedVersion: version,
      selectedDelivery: null,
    }))
  }, [])

  const selectDelivery = useCallback((delivery: DataDelivery | null) => {
    setState(prev => ({
      ...prev,
      selectedDelivery: delivery,
    }))
  }, [])

  const setSearchQuery = useCallback((query: string) => {
    setState(prev => ({
      ...prev,
      searchQuery: query,
      selectedProduct: null,
      selectedDataset: null,
      selectedDataObject: null,
      selectedVersion: null,
      selectedDelivery: null,
    }))
  }, [])

  const reset = useCallback(() => {
    setState({
      selectedProduct: null,
      selectedDataset: null,
      selectedDataObject: null,
      selectedVersion: null,
      selectedDelivery: null,
      searchQuery: '',
    })
  }, [])

  const searchResults = useCallback(
    (products: DataProduct[], datasets: DataSet[]) => {
      if (!state.searchQuery.trim()) {
        return { products, datasets }
      }

      const filteredProducts = products.filter(p =>
        matchesTokenizedSearch([
          p.name,
          p.description,
          ...(p.datasets || []).flatMap(ds => [
            ds.name,
            ds.description,
            ...(ds.dataObjects || []).flatMap(dobj => [dobj.name, dobj.description]),
          ]),
        ], state.searchQuery)
      )

      const filteredDatasets = datasets.filter(ds =>
        matchesTokenizedSearch([
          ds.name,
          ds.description,
          ...(ds.dataObjects || []).flatMap(dobj => [dobj.name, dobj.description]),
        ], state.searchQuery)
      )

      return { products: filteredProducts, datasets: filteredDatasets }
    },
    [state.searchQuery]
  )

  // Fetch standalone datasets from database
  useEffect(() => {
    const fetchStandaloneDatasets = async () => {
      if (!canUseAuthenticatedRequests) {
        setStandaloneDatasets([])
        return
      }

      try {
        const response = await fetch(`${apiBase}/data-sets?standalone=true`, getAuthRequestInit())
        if (!response.ok) {
          if (response.status === 401) {
            setStandaloneDatasets([])
            return
          }
          console.error('Failed to fetch standalone datasets')
          return
        }
        
        const datasets = unwrapPage(await response.json())
        const transformedDatasets: DataSet[] = datasets.map((ds: any) => ({
          id: ds.id,
          productId: undefined,
          name: ds.name,
          tags: normalizeTags(ds.tags || ds.tag_ids),
          description: ds.description || '',
          owner: ds.owner || '',
          createdAt: ds.created_at || '',
          workspaceId: ds.workspace_id || 'default',
          dataContractDownloadUrl: ds.data_contract_download_url || '',
          dataObjects: [],
        }))
        
        setStandaloneDatasets(transformedDatasets)
      } catch (error) {
        console.error('Error fetching standalone datasets:', error)
      }
    }
    
    fetchStandaloneDatasets()
  }, [apiBase, canUseAuthenticatedRequests, getAuthRequestInit])
  
  const { products: filteredProducts, datasets: filteredStandaloneDatasets } = searchResults(
    loadedProducts,
    standaloneDatasets
  )

  const value: DataProductContextType = {
    state,
    selectProduct,
    selectDataset,
    selectDataObject,
    selectVersion,
    selectDelivery,
    setSearchQuery,
    reset,
    filteredProducts,
    allProducts: loadedProducts,
    isLoadingProducts: isLoading,
    standaloneDatasets: filteredStandaloneDatasets,
    searchResults,
    loadDatasets,
    loadDataObjects,
    loadVersions,
    loadAttributes,
    isLoadingDatasets: (productId: string) => loadingDatasets.has(productId),
    isLoadingObjects: (datasetId: string) => loadingObjects.has(datasetId),
    isLoadingVersions: (objectId: string) => loadingVersions.has(objectId),
    isLoadingAttributes: (versionId: string) => loadingAttributes.has(versionId),
  }

  return (
    <DataProductContext.Provider value={value}>
      {children}
    </DataProductContext.Provider>
  )
}

export const useDataProduct = () => {
  const context = React.useContext(DataProductContext)
  if (!context) {
    throw new Error('useDataProduct must be used within DataProductProvider')
  }
  return context
}
