// Utilities to convert between snake_case and camelCase for keys and objects
export const toCamel = (s: string): string => {
  if (!s || typeof s !== 'string') return s
  return s.replace(/_([a-z0-9])/g, (_m, c) => (c || '').toUpperCase()).replace(/Pagerduty/g, 'PagerDuty')
}

export const toSnake = (s: string): string => {
  if (!s || typeof s !== 'string') return s
  return s.replace(/PagerDuty/g, 'Pagerduty').replace(/([A-Z])/g, '_$1').toLowerCase()
}

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  Object.prototype.toString.call(v) === '[object Object]'

export const snakeToCamel = <T = any>(input: unknown): T => {
  if (Array.isArray(input)) {
    return input.map((i) => snakeToCamel(i)) as unknown as T
  }
  if (isPlainObject(input)) {
    const out: Record<string, unknown> = {}
    for (const key of Object.keys(input as Record<string, unknown>)) {
      const val = (input as Record<string, unknown>)[key]
      out[toCamel(key)] = snakeToCamel(val)
    }
    return out as unknown as T
  }
  return input as unknown as T
}

export const camelToSnake = <T = any>(input: unknown): T => {
  if (Array.isArray(input)) {
    return input.map((i) => camelToSnake(i)) as unknown as T
  }
  if (isPlainObject(input)) {
    const out: Record<string, unknown> = {}
    for (const key of Object.keys(input as Record<string, unknown>)) {
      const val = (input as Record<string, unknown>)[key]
      out[toSnake(key)] = camelToSnake(val)
    }
    return out as unknown as T
  }
  return input as unknown as T
}

export default {
  toCamel,
  toSnake,
  snakeToCamel,
  camelToSnake,
}
