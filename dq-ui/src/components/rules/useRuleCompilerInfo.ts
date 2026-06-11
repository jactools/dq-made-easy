import { useEffect, useState } from 'react'
import { toApiGroupV1Base } from '../../config/api'

const unwrapPage = (responseBody: any): any[] =>
  Array.isArray(responseBody?.data) ? responseBody.data : (Array.isArray(responseBody) ? responseBody : [])

export interface LatestCompiledRuleInfo {
  ruleVersionId: string | null
  ruleVersionNumber: number | null
  compiledExpression: string | null
  compilerVersion: string | null
  compilerRevision: number | null
  compileStatus: string | null
  compiledAt: string | null
}

interface UseRuleCompilerInfoParams {
  authToken: string | null
  apiBaseUrl?: string
}

export const useRuleCompilerInfo = ({ authToken, apiBaseUrl }: UseRuleCompilerInfoParams) => {
  const [latestCompiledInfoByRuleId, setLatestCompiledInfoByRuleId] = useState<Record<string, LatestCompiledRuleInfo>>({})

  useEffect(() => {
    const loadCompiledExpressions = async () => {
      if (!authToken) {
        setLatestCompiledInfoByRuleId({})
        return
      }

      try {
        const response = await fetch(`${toApiGroupV1Base('rulebuilder', apiBaseUrl)}/rules/compiler-versions?page=1&limit=100`, {
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        })

        if (!response.ok) {
          if (response.status === 401) {
            setLatestCompiledInfoByRuleId({})
            return
          }
          return
        }

        const body = await response.json()
        const rows = unwrapPage(body)
        const compiledMap = rows.reduce<Record<string, LatestCompiledRuleInfo>>((acc, row) => {
          const ruleId = String(row?.ruleId || '').trim()
          if (!ruleId) return acc

          acc[ruleId] = {
            ruleVersionId: row?.ruleVersionId ? String(row.ruleVersionId) : null,
            ruleVersionNumber: typeof row?.ruleVersionNumber === 'number' ? row.ruleVersionNumber : null,
            compiledExpression: row?.compiledExpression ? String(row.compiledExpression) : null,
            compilerVersion: row?.compilerVersion ? String(row.compilerVersion) : null,
            compilerRevision: typeof row?.compilerRevision === 'number' ? row.compilerRevision : null,
            compileStatus: row?.compileStatus ? String(row.compileStatus) : null,
            compiledAt: row?.compiledAt ? String(row.compiledAt) : null,
          }

          return acc
        }, {})

        setLatestCompiledInfoByRuleId(compiledMap)
      } catch {
        setLatestCompiledInfoByRuleId({})
      }
    }

    void loadCompiledExpressions()
  }, [apiBaseUrl, authToken])

  return {
    latestCompiledInfoByRuleId,
  }
}