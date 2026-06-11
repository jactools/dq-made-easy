export const joinClassNames = (...classNames: Array<string | undefined | false>): string => {
  return classNames.filter(Boolean).join(' ')
}