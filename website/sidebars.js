/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    { type: 'doc', id: 'index', label: 'Overview' },
    { type: 'doc', id: 'introduction', label: 'Introduction' },
    {
      type: 'category',
      label: 'Getting started',
      collapsed: false,
      items: [
        { type: 'link', label: 'Installation', href: '/docs' },
        'configuration',
        'examples',
      ],
    },
    {
      type: 'category',
      label: 'Concepts',
      collapsed: false,
      items: [
        'architecture',
        'swarm_runtime',
        'memory_system',
        'tools',
        'providers',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      collapsed: false,
      items: [
        { type: 'doc', id: 'cli', label: 'CLI Reference' },
        { type: 'link', label: 'Configuration Schema', href: '/docs/configuration#schema-v1-format' },
      ],
    },
    {
      type: 'category',
      label: 'Contributing',
      collapsed: false,
      items: [
        'development',
        'release_checklist',
        'faq',
      ],
    },
  ],
};

module.exports = sidebars;
