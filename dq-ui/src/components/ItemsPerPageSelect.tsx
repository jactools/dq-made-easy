import React from 'react'
import { AppSelect } from './app-primitives'

interface ItemsPerPageSelectProps {
  id: string
  label: string
  value: number
  maxItems: number
  onChange: (value: number) => void
  showHint?: boolean
}

const getItemsPerPageOptions = (maxItems: number): number[] => {
  const normalizedMax = Math.max(5, maxItems || 5)
  const baseMarks = [5, 25, 50, 75, 100]
  const options = new Set<number>()

  baseMarks.forEach(mark => {
    if (mark <= normalizedMax) {
      options.add(mark)
    }
  })

  options.add(normalizedMax)

  return Array.from(options).sort((a, b) => a - b)
}

export const ItemsPerPageSelect: React.FC<ItemsPerPageSelectProps> = ({
  id,
  label,
  value,
  maxItems,
  onChange,
  showHint = false,
}) => {
  const normalizedMax = Math.max(5, maxItems || 5)
  const options = getItemsPerPageOptions(normalizedMax)
  const clampedValue = Math.min(Math.max(value, 5), normalizedMax)

  return (
    <AppSelect
      id={id}
      label={label}
      value={String(clampedValue)}
      onChange={(nextValue) => onChange(parseInt(nextValue, 10))}
      options={options.map((option) => ({ value: String(option), label: String(option) }))}
      placeholderLabel=""
      hint={showHint ? `Admin cap: ${normalizedMax} items` : undefined}
      fieldClassName="list-select"
    />
  )
}
