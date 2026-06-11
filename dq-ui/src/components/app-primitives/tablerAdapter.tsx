import React from 'react'
import {
  IconArrowRight,
  IconArrowUp,
  IconBellFilled,
  IconCheck,
  IconCircleCheck,
  IconDatabase,
  IconFolder,
  IconInfoCircleFilled,
  IconPackage,
  IconSearch,
  IconSettings,
  IconSquareArrowRightFilled,
  IconUsers,
  IconX,
} from '@tabler/icons-react'
import type { AppIconName } from './appIconRegistry'

type ProviderIconComponent = React.ComponentType<React.SVGProps<SVGSVGElement> & { size?: number; strokeWidth?: number }>

const TABLER_ICON_COMPONENTS: Partial<Record<AppIconName, ProviderIconComponent>> = {
  'arrow-right': IconArrowRight,
  'arrow-up': IconArrowUp,
  bell: IconBellFilled,
  check: IconCheck,
  'check-circle': IconCircleCheck,
  close: IconX,
  database: IconDatabase,
  folder: IconFolder,
  'info-circle': IconInfoCircleFilled,
  package: IconPackage,
  search: IconSearch,
  settings: IconSettings,
  'square-arrow-right': IconSquareArrowRightFilled,
  users: IconUsers,
}

export const TABLER_ICON_NAMES = Object.keys(TABLER_ICON_COMPONENTS) as AppIconName[]

export const getTablerIconComponent = (name: AppIconName): ProviderIconComponent | null => TABLER_ICON_COMPONENTS[name] || null