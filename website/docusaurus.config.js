/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'Hivemind',
  tagline: 'Distributed AI Swarm Runtime',
  favicon: 'img/favicon.svg',
  url: 'https://hivemind.rithul.dev',
  baseUrl: '/',
  organizationName: 'rithulkamesh',
  projectName: 'hivemind',
  trailingSlash: false,
  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: 'docs',
          sidebarPath: './sidebars.js',
          editUrl: 'https://github.com/rithulkamesh/hivemind/edit/main/docs/',
          showLastUpdateTime: true,
          lastVersion: 'current',
          versions: {
            current: {
              label: 'Latest',
              path: '',
            },
          },
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      },
    ],
  ],

  themeConfig: {
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Hivemind',
      logo: {
        alt: 'Hivemind',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docs',
          position: 'left',
          label: 'Docs',
        },
        {
          href: 'https://github.com/rithulkamesh/hivemind',
          position: 'right',
          className: 'header-github-link',
          'aria-label': 'GitHub',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            { label: 'Introduction', to: '/docs/introduction' },
            { label: 'Configuration', to: '/docs/configuration' },
            { label: 'CLI', to: '/docs/cli' },
            { label: 'Architecture', to: '/docs/architecture' },
          ],
        },
        {
          title: 'Project',
          items: [
            { label: 'GitHub', href: 'https://github.com/rithulkamesh/hivemind' },
            { label: 'PyPI', href: 'https://pypi.org/project/hivemind-ai/' },
          ],
        },
      ],
      copyright: `Hivemind. Distributed AI Swarm Runtime.`,
    },
    prism: {
      theme: require('prism-react-renderer').themes.github,
      darkTheme: require('prism-react-renderer').themes.vsDark,
      additionalLanguages: ['bash', 'toml', 'python'],
    },
  },

  plugins: [],
};

module.exports = config;
