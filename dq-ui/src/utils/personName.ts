type PersonNameSource = {
  firstName?: unknown
  lastName?: unknown
  first_name?: unknown
  last_name?: unknown
  name?: unknown
}

const clean = (value: unknown): string => String(value || '').trim()

export const resolvePersonName = (value: PersonNameSource | null | undefined) => {
  let firstName = clean(value?.firstName ?? value?.first_name)
  let lastName = clean(value?.lastName ?? value?.last_name)

  if ((!firstName || !lastName) && clean(value?.name)) {
    const parts = clean(value?.name).split(/\s+/).filter(Boolean)
    firstName = firstName || parts[0] || ''
    lastName = lastName || parts.slice(1).join(' ')
  }

  return {
    firstName,
    lastName,
    displayName: [firstName, lastName].filter(Boolean).join(' ').trim(),
  }
}

export const formatPersonName = (firstName: unknown, lastName: unknown, fallback?: unknown): string => {
  const displayName = [clean(firstName), clean(lastName)].filter(Boolean).join(' ').trim()
  if (displayName) {
    return displayName
  }
  return clean(fallback)
}