/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'devsper',
  tagline: 'The AI swarm platform for developers',
  favicon: 'img/favicon.svg',
  url: 'https://docs.devsper.com',
  baseUrl: '/',
  organizationName: 'devsper-com',
  projectName: 'runtime',
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
          'devsper is a distributed AI swarm runtime. Orchestrate multi-agent systems with a swarm execution model: tasks become a DAG, then run in parallel. pip install devsper',
      },
    },
    {
      tagName: 'meta',
      attributes: {
        property: 'og:description',
        content:
          'devsper is a distributed AI swarm runtime. Orchestrate multi-agent systems with a swarm execution model: tasks become a DAG, then run in parallel. pip install devsper',
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
            name: 'devsper',
            url: 'https://devsper.com',
            logo: 'https://docs.devsper.com/img/logo.svg',
            description: 'The AI swarm platform for developers',
          },
          {
            '@type': 'SoftwareApplication',
            name: 'devsper',
            applicationCategory: 'DeveloperApplication',
            operatingSystem: 'Windows, macOS, Linux',
            description:
              'Orchestrate multi-agent AI systems with a swarm execution model. Tasks become a DAG and run in parallel. Install: pip install devsper',
            url: 'https://docs.devsper.com',
            downloadUrl: 'https://pypi.org/project/devsper/',
          },
        ],
      }),
    },
  ],

  customFields: {
    registryUrl: 'https://registry.devsper.com',
  },

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: 'docs',
          sidebarPath: './sidebars.js',
          editUrl: 'https://github.com/devsper-com/runtime/edit/main/website/',
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
      { name: 'keywords', content: 'devsper, AI, multi-agent, swarm, distributed AI, LLM, agents, Python, DAG, orchestration, plugins, registry' },
      { name: 'twitter:card', content: 'summary_large_image' },
      { property: 'og:type', content: 'website' },
      { property: 'og:locale', content: 'en_US' },
    ],

    navbar: {
      title: 'devsper',
      hideOnScroll: true,
      logo: {
        alt: 'devsper',
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
          href: 'https://registry.devsper.com',
          position: 'left',
          label: 'Registry',
        },
        {
          href: 'https://github.com/devsper-com/runtime',
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
