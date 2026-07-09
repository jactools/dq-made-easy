const siteUrl = process.env.DOCS_SITE_URL || 'http://127.0.0.1'

/** @type {import('@docusaurus/types').Config} */
module.exports = {
  title: 'DQ Made Easy Docs',
  tagline: 'Public documentation for dq-made-easy',
  favicon: 'img/favicon.svg',
  url: siteUrl,
  baseUrl: '/docs/',
  organizationName: 'dq-rulebuilder',
  projectName: 'dq-ui-docs-site',
  onBrokenLinks: 'warn',
  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },
  trailingSlash: true,
  presets: [
    [
      require.resolve('@docusaurus/preset-classic'),
      /** @type {import('@docusaurus/preset-classic').Options} */ ({
        docs: {
          routeBasePath: '/',
          sidebarPath: require.resolve('./sidebars.js'),
        },
        blog: false,
      }),
    ],
  ],
  plugins: [],
  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */ ({
      colorMode: {
        defaultMode: 'light',
        disableSwitch: false,
        respectPrefersColorScheme: true,
      },
      navbar: {
        title: 'DQ Made Easy Docs',
        logo: {
          alt: 'DQ Made Easy',
          src: 'img/logo.svg',
        },
        items: [
          { type: 'doc', docId: 'feature-plans', label: 'Feature Plans', position: 'left' },
          { type: 'doc', docId: 'technical-references', label: 'Technical', position: 'left' },
          { type: 'doc', docId: 'release-notes', label: 'Releases', position: 'left' },
          { type: 'doc', docId: 'user-manuals', label: 'Manuals', position: 'left' },
          { type: 'doc', docId: 'features/FEATURES', label: 'Status & Roadmap', position: 'left' },
          { label: 'EDRs', to: '/engineering-decisions/', position: 'left' },
          { label: 'Architecture', to: '/architecture/', position: 'left' },
          { type: 'doc', docId: 'api-reference', label: 'API', position: 'right' },
        ],
      },
      footer: {
        links: [
          {
            title: 'Docs',
            items: [
              { label: 'Overview', to: '/' },
              { label: 'Feature Plans', to: '/feature-plans' },
            ],
          },
          {
            title: 'Reference',
            items: [
              { label: 'User manuals', to: '/user-manuals' },
              { label: 'API reference', to: '/api-reference' },
              { label: 'Technical references', to: '/technical-references' },
            ],
          },
        ],
        copyright: `Copyright ${new Date().getFullYear()} dq-made-easy maintainers.`,
      },
    }),
}