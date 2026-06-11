/**
 * Hook to check if preview features are enabled
 */

import { useSettings } from './useContexts'

export const usePreviewFeatures = () => {
  const settings = useSettings()
  
  const isPreviewEnabled = settings.displaySettings?.participateInPreviews ?? false
  
  return {
    isPreviewEnabled,
    isFeatureEnabled: (featureName: string) => {
      // For now, all preview features are controlled by the same flag
      // In the future, could add per-feature flags
      return isPreviewEnabled
    }
  }
}
