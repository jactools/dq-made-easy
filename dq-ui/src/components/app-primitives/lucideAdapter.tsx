import React from 'react'
import { ArrowRight, ArrowUp, Bell, Check, CircleCheck, Database, Folder, Info, Package, Search, Settings, SquareArrowRight, Users, X } from 'lucide-react'
import type { AppIconName } from './appIconRegistry'

type ProviderIconComponent = React.ComponentType<React.SVGProps<SVGSVGElement> & { size?: number; strokeWidth?: number }>

const LUCIDE_ICON_COMPONENTS: Partial<Record<AppIconName, ProviderIconComponent>> = {
  'arrow-right': ArrowRight,
  'arrow-up': ArrowUp,
  bell: Bell,
  check: Check,
  'check-circle': CircleCheck,
  close: X,
  database: Database,
  folder: Folder,
  'info-circle': Info,
  package: Package,
  search: Search,
  settings: Settings,
  'square-arrow-right': SquareArrowRight,
  users: Users,
}

export const LUCIDE_ICON_NAMES = Object.keys(LUCIDE_ICON_COMPONENTS) as AppIconName[]

export const getLucideIconComponent = (name: AppIconName): ProviderIconComponent | null => LUCIDE_ICON_COMPONENTS[name] || null