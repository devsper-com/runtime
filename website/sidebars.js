/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    'index',
    'introduction',
    {
      type: 'category',
      label: 'Getting started',
      items: ['configuration', 'cli', 'examples'],
    },
    {
      type: 'category',
      label: 'Concepts',
      items: [
        'architecture',
        'swarm_runtime',
        'memory_system',
        'tools',
        'providers',
      ],
    },
    'tui',
    'development',
    'release_checklist',
    'faq',
  ],
};

module.exports = sidebars;
