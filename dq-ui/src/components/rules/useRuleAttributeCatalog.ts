import { useEffect, useState } from 'react'
import { toApiGroupV1Base } from '../../config/api'

const unwrapPage = (responseBody: any): any[] =>
  Array.isArray(responseBody?.data) ? responseBody.data : (Array.isArray(responseBody) ? responseBody : [])

export interface ResolvedRuleAttribute {
  id: string
  name: string
  versionId?: string
  dataObjectVersion?: string
  dataObjectId?: string
  dataObjectName?: string
  datasetName?: string
  dataProductName?: string
  workspaceId?: string
  sourceKind?: string
  sourceName?: string
  sourceVersionLabel?: string
}

interface UseRuleAttributeCatalogParams {
  authToken: string | null
  apiBaseUrl?: string
  refreshKey?: unknown
}

export const useRuleAttributeCatalog = ({ authToken, apiBaseUrl, refreshKey }: UseRuleAttributeCatalogParams) => {
  const [attributeCatalog, setAttributeCatalog] = useState<Record<string, ResolvedRuleAttribute>>({})

  useEffect(() => {
    if (!authToken) {
      setAttributeCatalog({})
      return
    }

    const baseUrl = toApiGroupV1Base('data-catalog', apiBaseUrl)
    const authHeaders = { Authorization: `Bearer ${authToken}` }

    const fetchAllPages = async (endpoint: string): Promise<any[]> => {
      const limit = 100
      let page = 1
      let rows: any[] = []

      while (true) {
        const separator = endpoint.includes('?') ? '&' : '?'
        const response = await fetch(`${baseUrl}/${endpoint}${separator}page=${page}&limit=${limit}`, {
          headers: authHeaders,
        })

        if (!response.ok) {
          throw new Error(`Failed to fetch ${endpoint}`)
        }

        const body = await response.json()
        const chunk = unwrapPage(body)
        const total = Number(body?.total ?? rows.length + chunk.length)
        rows = rows.concat(chunk)

        if (chunk.length === 0 || rows.length >= total || chunk.length < limit) {
          break
        }

        page += 1
      }

      return rows
    }

    const loadAttributeCatalog = async () => {
      try {
        const attributes = await fetchAllPages('attributes-catalog')
        const [dataObjectsResult, dataSetsResult, dataProductsResult] = await Promise.allSettled([
          fetchAllPages('data-objects-catalog'),
          fetchAllPages('data-sets'),
          fetchAllPages('data-products'),
        ])

        const dataObjects = dataObjectsResult.status === 'fulfilled' ? dataObjectsResult.value : []
        const dataSets = dataSetsResult.status === 'fulfilled' ? dataSetsResult.value : []
        const dataProducts = dataProductsResult.status === 'fulfilled' ? dataProductsResult.value : []

        const productsById = dataProducts.reduce<Record<string, any>>((acc, product) => {
          acc[product.id] = product
          return acc
        }, {})

        const dataSetsById = dataSets.reduce<Record<string, any>>((acc, dataSet) => {
          acc[dataSet.id] = dataSet
          return acc
        }, {})

        const dataObjectsById = dataObjects.reduce<Record<string, any>>((acc, dataObject) => {
          acc[dataObject.id] = dataObject
          return acc
        }, {})

        const nextCatalog = attributes.reduce<Record<string, ResolvedRuleAttribute>>((acc, attribute) => {
          const attributeId = String(attribute.id || '').trim()
          const versionId = String(attribute.version_id ?? attribute.versionId ?? '').trim()
          const dataObjectId = String(attribute.data_object_id ?? attribute.dataObjectId ?? '').trim()
          const sourceKind = String(attribute.source_kind ?? attribute.sourceKind ?? '').trim() || undefined
          const sourceName = String(attribute.source_name ?? attribute.sourceName ?? '').trim() || undefined
          const sourceVersionLabel = String(attribute.source_version_label ?? attribute.sourceVersionLabel ?? '').trim() || undefined
          if (!attributeId || !dataObjectId) {
            return acc
          }

          const dataObject = dataObjectsById[dataObjectId]
          const dataSetId = dataObject?.dataset_id ?? dataObject?.data_set_id
          const dataSet = dataSetId ? dataSetsById[dataSetId] : undefined
          const dataProductId = dataSet?.product_id ?? dataSet?.data_product_id
          const dataProduct = dataProductId ? productsById[dataProductId] : undefined
          const workspaceId = String(
            attribute.workspace_id ??
            attribute.workspaceId ??
            dataSet?.workspace_id ??
            dataSet?.workspaceId ??
            dataProduct?.workspace_id ??
            dataProduct?.workspaceId ??
            '',
          ).trim() || undefined

          acc[attributeId] = {
            id: attributeId,
            name: attribute.name || attributeId,
            versionId,
            dataObjectVersion: String(
              sourceVersionLabel ??
              attribute.version ??
              attribute.data_object_version ??
              attribute.dataObjectVersion ??
              '',
            ).trim() || undefined,
            dataObjectId,
            dataObjectName: dataObject?.name || (sourceKind === 'data_asset' ? sourceName : undefined),
            datasetName: dataSet?.name,
            dataProductName: dataProduct?.name,
            workspaceId,
            sourceKind,
            sourceName,
            sourceVersionLabel,
          }

          return acc
        }, {})

        setAttributeCatalog(nextCatalog)
      } catch {
        setAttributeCatalog({})
      }
    }

    void loadAttributeCatalog()
  }, [apiBaseUrl, authToken, refreshKey])

  return {
    attributeCatalog,
  }
}