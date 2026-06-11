const path = require('path')
const { buildSidebarItems } = require('./sidebars-utils')

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
module.exports = {
	releasesSidebar: buildSidebarItems(path.join(__dirname, 'docs/releases'), '', 'root'),
}