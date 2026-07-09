const path = require('path')
const { buildSidebarItems } = require('./sidebars-utils')

const docsRoot = path.join(__dirname, 'docs')

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
module.exports = {
  tutorialSidebar: [
    {
      type: 'category',
      label: 'Start Here',
      items: ['index'],
    },
    {
      type: 'category',
      label: 'Portal Pages',
      items: ['feature-plans', 'technical-references', 'release-notes', 'user-manuals', 'api-reference'],
    },
    {
      type: 'category',
      label: 'Features',
      items: buildSidebarItems(docsRoot, 'features'),
    },
    {
      type: 'category',
      label: 'Releases',
      items: buildSidebarItems(docsRoot, 'releases'),
    },
    {
      type: 'category',
      label: 'Engineering Decisions',
      items: buildSidebarItems(docsRoot, 'engineering-decisions'),
    },
    {
      type: 'category',
      label: 'Architecture',
      items: buildSidebarItems(docsRoot, 'architecture'),
    },
    {
      type: 'category',
      label: 'Test Proof',
      items: buildSidebarItems(docsRoot, 'test-proof'),
    },
    {
      type: 'category',
      label: 'Implementation Details',
      items: buildSidebarItems(docsRoot, 'implementation-details'),
    },
    {
      type: 'category',
      label: 'Technical',
      items: buildSidebarItems(docsRoot, 'technical'),
    },
    {
      type: 'category',
      label: 'Contracts',
      items: buildSidebarItems(docsRoot, 'contracts'),
    },
    {
      type: 'category',
      label: 'Runbooks',
      items: buildSidebarItems(docsRoot, 'runbooks'),
    },
    {
      type: 'category',
      label: 'Fixes',
      items: buildSidebarItems(docsRoot, 'fixes'),
    },
    {
      type: 'category',
      label: 'User Manual Source',
      items: buildSidebarItems(docsRoot, 'user-manuals'),
    },
  ],
}