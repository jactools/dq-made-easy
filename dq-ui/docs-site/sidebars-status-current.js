const path = require('path')
const { buildSidebarItems } = require('./sidebars-utils')

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
module.exports = {
	statusCurrentSidebar: buildSidebarItems(path.join(__dirname, 'docs/status/current'), '', 'root'),
}