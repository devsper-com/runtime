/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'hivemind',
  tagline: 'The AI swarm runtime for complex tasks',
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
        href: 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'stylesheet',
        href: 'https://cdn.jsdelivr.net/npm/geist@1/dist/font/css/geist-sans.min.css',
      },
    },
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
    {
      tagName: 'script',
      attributes: { type: 'application/ld+json' },
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': 'Organization',
            name: 'hivemind',
            url: 'https://hivemind.rithul.dev',
            logo: 'https://hivemind.rithul.dev/img/logo.svg',
            description: 'The AI swarm runtime for complex tasks',
          },
          {
            '@type': 'SoftwareApplication',
            name: 'hivemind',
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

  customFields: {
    registryUrl: 'https://registry.hivemind.rithul.dev',
  },

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: 'docs',
          sidebarPath: './sidebars.js',
          editUrl: 'https://github.com/rithulkamesh/hivemind/edit/main/website/',
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
      disableSwitch: true,
      respectPrefersColorScheme: false,
    },

    image: 'img/banner.png',
    metadata: [
      { name: 'keywords', content: 'hivemind, AI, multi-agent, swarm, distributed AI, LLM, agents, Python, DAG, orchestration, plugins, registry' },
      { name: 'twitter:card', content: 'summary_large_image' },
      { name: 'twitter:site', content: '@rithulkamesh' },
      { property: 'og:type', content: 'website' },
      { property: 'og:locale', content: 'en_US' },
    ],

    navbar: {
      title: 'hivemind',
      hideOnScroll: true,
      logo: {
        alt: 'Hivemind',
        src: 'img/logo.svg',
        srcDark: 'img/logo_dark.svg',
      },
      items: [
        {
          to: '/docs/',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/docs/plugins/overview',
          position: 'left',
          label: 'Plugins',
        },
        {
          href: 'https://registry.hivemind.rithul.dev',
          position: 'left',
          label: 'Registry',
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

    // Footer is handled by the landing page component; disable the Docusaurus footer
    footer: undefined,

    prism: {
      theme: require('prism-react-renderer').themes.github,
      darkTheme: require('prism-react-renderer').themes.vsDark,
      additionalLanguages: ['bash', 'toml', 'python', 'go'],
    },

    sidebar: {
      hideable: false,
    },
  },

  plugins: [],
};

module.exports = config;
