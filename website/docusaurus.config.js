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

  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  headTags: [
    {
      tagName: 'link',
      attributes: {
        rel: 'preconnect',
        href: 'https://fonts.googleapis.com',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'preconnect',
        href: 'https://fonts.gstatic.com',
        crossorigin: 'anonymous',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'stylesheet',
        href: 'https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000&family=JetBrains+Mono:wght@400;500;600&display=swap',
      },
    },
    // SEO: default meta description and og:description (Docusaurus 3 does not allow root "description")
    {
      tagName: 'meta',
      attributes: {
        name: 'description',
        content:
          'Hivemind is a distributed AI swarm runtime. Orchestrate multi-agent systems with a swarm execution model: tasks become a DAG, then run in parallel. pip install hivemind-ai',
      },
    },
    {
      tagName: 'meta',
      attributes: {
        property: 'og:description',
        content:
          'Hivemind is a distributed AI swarm runtime. Orchestrate multi-agent systems with a swarm execution model: tasks become a DAG, then run in parallel. pip install hivemind-ai',
      },
    },
    // JSON-LD for SEO (Organization + SoftwareApplication)
    {
      tagName: 'script',
      attributes: { type: 'application/ld+json' },
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': 'Organization',
            name: 'Hivemind',
            url: 'https://hivemind.rithul.dev',
            logo: 'https://hivemind.rithul.dev/img/logo.svg',
            description: 'Distributed AI Swarm Runtime',
          },
          {
            '@type': 'SoftwareApplication',
            name: 'Hivemind',
            applicationCategory: 'DeveloperApplication',
            operatingSystem: 'Windows, macOS, Linux',
            description:
              'Orchestrate multi-agent AI systems with a swarm execution model. Tasks become a DAG and run in parallel. Install: pip install hivemind-ai',
            url: 'https://hivemind.rithul.dev',
            downloadUrl: 'https://pypi.org/project/hivemind-ai/',
          },
        ],
      }),
    },
  ],

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
      respectPrefersColorScheme: false,
    },

    // Announcement bar (banner) – edit content as needed
    announcementBar: {
      id: 'announcement',
      content: 'Documentation for the Hivemind distributed AI swarm runtime. <a href="/docs/introduction">Get started</a>',
      backgroundColor: '#0f172a',
      textColor: '#e2e8f0',
      isCloseable: true,
    },

    // SEO: default social image and meta
    image: 'img/logo.svg',
    metadata: [
      { name: 'keywords', content: 'hivemind, AI, multi-agent, swarm, distributed AI, LLM, agents, Python, DAG, orchestration' },
      { name: 'twitter:card', content: 'summary_large_image' },
      { name: 'twitter:site', content: '@rithulkamesh' },
      { property: 'og:type', content: 'website' },
      { property: 'og:locale', content: 'en_US' },
    ],

    navbar: {
      title: 'Hivemind',
      hideOnScroll: true,
      logo: {
        alt: 'Hivemind',
        src: 'img/logo.svg',
        srcDark: 'img/logo_dark.svg',
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
          label: 'GitHub',
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
    sidebar: {
      hideable: false,
    },
  },

  plugins: [],
};

module.exports = config;
