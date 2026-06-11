export function getPagePreferences(
  user: any,
  pageKey: string,
  legacyKeys?: string[],
) {
  if (!user) return null;
  const prefs = (user && (user as any).preferences) || {};
  // direct key first
  if (prefs[pageKey] && Array.isArray(prefs[pageKey])) return prefs[pageKey];
  // try legacy or alternate keys
  if (legacyKeys && Array.isArray(legacyKeys)) {
    for (const k of legacyKeys) {
      if (prefs[k] && Array.isArray(prefs[k])) return prefs[k];
    }
  }
  return null;
}

export function preferenceKeyFor(pageKey: string) {
  // normalize a few known aliases to canonical keys used by ColumnSelector
  const map: Record<string, string> = {
    rulesColumns: "rules",
    rules: "rules",
    data_object: "data_objects",
    data_objects: "data_objects",
    approvals: "approvals",
    approval_audit: "approval_audit",
  };
  return map[pageKey] || pageKey;
}

export default { getPagePreferences, preferenceKeyFor };
