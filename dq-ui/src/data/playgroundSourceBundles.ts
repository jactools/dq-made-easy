export type PlaygroundSourceBundle = {
  readonly bundleId: string
  readonly title: string
  readonly sourceUrl: string
  readonly licenseName: string
  readonly licenseUrl?: string
  readonly description: string
}

export const PLAYGROUND_SOURCE_BUNDLES: readonly PlaygroundSourceBundle[] = [
  {
    bundleId: 'ons-national-statistics',
    title: 'Office for National Statistics',
    sourceUrl: 'https://www.ons.gov.uk/',
    licenseName: 'Open Government Licence v3.0',
    licenseUrl: 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',
    description: 'UK population, inflation, GDP, and labour-market series.',
  },
  {
    bundleId: 'abs-national-statistics',
    title: 'Australian Bureau of Statistics',
    sourceUrl: 'https://www.abs.gov.au/',
    licenseName: 'Creative Commons Attribution 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by/4.0/',
    description: 'Population, CPI, GDP, earnings, unemployment, and regional datasets.',
  },
  {
    bundleId: 'stats-nz-national-statistics',
    title: 'Stats NZ',
    sourceUrl: 'https://www.stats.govt.nz/',
    licenseName: 'Creative Commons Attribution 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by/4.0/',
    description: 'Population, GDP, CPI, unemployment, trade, and regional summaries.',
  },
  {
    bundleId: 'ecb-finance-terminology',
    title: 'ECB Data Portal',
    sourceUrl: 'https://data.ecb.europa.eu/',
    licenseName: 'ECB free access and free reuse',
    description:
      'Euro exchange rates, yield curves, money market reporting, investment funds, monetary financial institutions, and banking-supervision-related statistics.',
  },
  {
    bundleId: 'boe-finance-terminology',
    title: 'Bank of England Database',
    sourceUrl: 'https://www.bankofengland.co.uk/boeapps/database/',
    licenseName: 'Open Government Licence v3.0',
    licenseUrl: 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',
    description:
      'Exchange rates, yield curves, SONIA, money and credit, capital issuance, financial derivative positions, monetary financial institutions, and banking-sector regulatory capital.',
  },
] as const