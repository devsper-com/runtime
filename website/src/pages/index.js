import React, { useState, useEffect, useRef } from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';

/* ------------------------------------------------------------------ */
/*  Intersection Observer hook – triggers fade-in on scroll            */
/* ------------------------------------------------------------------ */
function useInView(options = {}) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.unobserve(el);
        }
      },
      { threshold: 0.15, ...options },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, inView];
}

/* ------------------------------------------------------------------ */
/*  Section 1 — Hero                                                   */
/* ------------------------------------------------------------------ */
const terminalText =
  '$ hivemind run "Research the top 5 AI papers this week,\n' +
  '    summarize each, and draft a newsletter"\n' +
  '\u28FE Planning... spawning 6 agents\n' +
  '\u2713 research_agent_1  found 847 papers (2.1s)\n' +
  '\u2713 research_agent_2  filtered to top 5  (1.8s)\n' +
  '\u2713 summarizer_1      GPT-4o summary done (3.2s)\n' +
  '...\n' +
  '\u2713 Complete \u2014 newsletter.md written (12.4s)';

function HeroTerminal() {
  const [charCount, setCharCount] = useState(0);

  useEffect(() => {
    if (charCount >= terminalText.length) return;
    const delay = charCount === 0 ? 400 : 12;
    const t = setTimeout(() => setCharCount((c) => c + 1), delay);
    return () => clearTimeout(t);
  }, [charCount]);

  const visible = terminalText.slice(0, charCount);
  const lines = visible.split('\n');

  return (
    <div className="hero-terminal">
      <div className="hero-terminal-header">
        <span className="hero-terminal-dot red" />
        <span className="hero-terminal-dot yellow" />
        <span className="hero-terminal-dot green" />
        <span className="hero-terminal-title">terminal</span>
      </div>
      <div className="hero-terminal-body">
        {lines.map((line, i) => {
          let cls = 'term-dim';
          if (line.startsWith('$')) cls = 'term-prompt';
          else if (line.startsWith('\u2713')) cls = 'term-success';
          else if (line.startsWith('\u28FE')) cls = 'term-dim';
          return (
            <div key={i} className={`term-line ${cls}`}>
              {line}
            </div>
          );
        })}
        {charCount < terminalText.length && (
          <span className="term-cursor">_</span>
        )}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="hm-hero">
      <div className="hm-hero-grid" aria-hidden="true" />
      <div className="hm-hero-glow" aria-hidden="true" />

      <div className="hm-hero-inner">
        <div className="hm-hero-content">
          <Link to="/docs/changelog" className="hm-badge hm-fade-up hm-delay-1">
            v2.3 &mdash; Now with multimodal agents &rarr;
          </Link>

          <h1 className="hm-hero-h1 hm-fade-up hm-delay-0">
            The AI swarm runtime<br />for complex tasks
          </h1>

          <p className="hm-hero-sub hm-fade-up hm-delay-2">
            hivemind breaks any task into a DAG of agents,
            runs them in parallel, and synthesizes the results.
          </p>

          <div className="hm-hero-ctas hm-fade-up hm-delay-2">
            <Link
              to="/docs/getting-started/installation"
              className="hm-btn hm-btn-primary"
            >
              Get started
            </Link>
            <Link
              to="https://github.com/rithulkamesh/hivemind"
              className="hm-btn hm-btn-ghost"
            >
              View on GitHub
            </Link>
          </div>

          <div className="hm-hero-terminal-wrap hm-fade-up hm-delay-3">
            <HeroTerminal />
          </div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 2 — Feature grid                                           */
/* ------------------------------------------------------------------ */
const features = [
  {
    icon: '\u26A1',
    title: 'Parallel execution',
    desc: 'Tasks run as a DAG \u2014 independent agents fire simultaneously.',
  },
  {
    icon: '\uD83E\uDDE0',
    title: 'Persistent memory',
    desc: 'Agents remember across runs. Vector search over past context.',
  },
  {
    icon: '\uD83D\uDD27',
    title: 'Tool ecosystem',
    desc: '100+ built-in tools. Extend with plugins from the registry.',
  },
  {
    icon: '\uD83D\uDD04',
    title: 'Self-healing',
    desc: 'Failed tasks are automatically diagnosed and retried with a new strategy.',
  },
  {
    icon: '\uD83D\uDCCA',
    title: 'Run intelligence',
    desc: 'Cost tracking, bottleneck analysis, critical path visualization.',
  },
  {
    icon: '\uD83C\uDF10',
    title: 'Distributed',
    desc: 'Scale across nodes. Redis-backed, Rust worker, single binary to start.',
  },
];

function FeatureGrid() {
  const [ref, inView] = useInView();
  return (
    <section ref={ref} className={`hm-features ${inView ? 'hm-visible' : ''}`}>
      <h2 className="hm-section-heading">
        Everything you need to build with AI agents
      </h2>
      <p className="hm-section-subheading">
        Built for production. Designed for developers.
      </p>
      <div className="hm-feature-grid">
        {features.map((f, i) => (
          <div
            key={f.title}
            className="hm-feature-card"
            style={{ transitionDelay: `${i * 80}ms` }}
          >
            <span className="hm-feature-icon">{f.icon}</span>
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 3 — Code example tabs                                      */
/* ------------------------------------------------------------------ */
const codeTabs = [
  {
    id: 'run',
    label: 'Run a task',
    lang: 'python',
    code: `import hivemind

result = hivemind.run(
    "Analyze this CSV and write a report with charts",
    files=["sales_data.csv"],
    model="claude-sonnet-4",
)
print(result.output)   # report.md written`,
  },
  {
    id: 'workflow',
    label: 'Write a workflow',
    lang: 'toml',
    code: `[workflow.research_report]
name = "Research Report"
version = "1.0"

[[workflow.research_report.steps]]
id = "research"
task = "Find the latest papers on {input.topic}"

[[workflow.research_report.steps]]
id = "summarize"
task = "Summarize each paper in 2 paragraphs"
depends_on = ["research"]

[[workflow.research_report.steps]]
id = "draft"
task = "Draft a report combining all summaries"
depends_on = ["summarize"]`,
  },
  {
    id: 'plugin',
    label: 'Build a plugin',
    lang: 'python',
    code: `from hivemind.tools.base import Tool
from hivemind.tools.registry import register

class SearchTool(Tool):
    name = "web_search"
    description = "Search the web for a query"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"}
        },
        "required": ["query"],
    }

    def run(self, **kwargs) -> str:
        return search(kwargs["query"])

register(SearchTool())`,
  },
];

function CodeTabs() {
  const [active, setActive] = useState('run');
  const [ref, inView] = useInView();

  return (
    <section
      ref={ref}
      className={`hm-code-section ${inView ? 'hm-visible' : ''}`}
    >
      <h2 className="hm-section-heading">
        Simple to start. Powerful at scale.
      </h2>
      <div className="hm-code-tabs">
        <div className="hm-tab-bar" role="tablist">
          {codeTabs.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={active === t.id}
              className={`hm-tab ${active === t.id ? 'hm-tab-active' : ''}`}
              onClick={() => setActive(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="hm-tab-content">
          {codeTabs.map((t) => (
            <pre
              key={t.id}
              className={`hm-code-block ${active === t.id ? 'hm-code-visible' : ''}`}
              aria-hidden={active !== t.id}
            >
              <code>{t.code}</code>
            </pre>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 4 — Registry callout                                       */
/* ------------------------------------------------------------------ */
function RegistryCallout() {
  const [ref, inView] = useInView();
  return (
    <section
      ref={ref}
      className={`hm-registry ${inView ? 'hm-visible' : ''}`}
    >
      <div className="hm-registry-card">
        <div className="hm-registry-text">
          <h2>Share tools with the ecosystem</h2>
          <p>
            Publish plugins to the hivemind registry. One command to install,
            one command to publish. pip-compatible.
          </p>
          <div className="hm-registry-links">
            <Link to="https://registry.hivemind.rithul.dev" className="hm-link-arrow">
              Browse registry &rarr;
            </Link>
            <Link to="/docs/plugins/publishing" className="hm-link-arrow">
              Publish your first plugin &rarr;
            </Link>
          </div>
        </div>
        <div className="hm-registry-terminal">
          <div className="hero-terminal">
            <div className="hero-terminal-header">
              <span className="hero-terminal-dot red" />
              <span className="hero-terminal-dot yellow" />
              <span className="hero-terminal-dot green" />
            </div>
            <div className="hero-terminal-body">
              <div className="term-line term-prompt">
                $ hivemind reg install hivemind-plugin-browseruse
              </div>
              <div className="term-line term-success">
                {'\u2713'} Installed 3 tools: browse, click, extract_text
              </div>
              <div className="term-line" />
              <div className="term-line term-prompt">
                $ hivemind run "Book me a flight to Tokyo next Friday"
              </div>
              <div className="term-line term-dim">
                {'\u28FE'} Planning...
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 5 — Footer                                                 */
/* ------------------------------------------------------------------ */
function Footer() {
  return (
    <footer className="hm-footer">
      <div className="hm-footer-inner">
        <div className="hm-footer-col hm-footer-brand">
          <h4>hivemind</h4>
          <p>The AI swarm runtime for complex tasks.</p>
          <Link to="https://github.com/rithulkamesh/hivemind">
            GitHub
          </Link>
        </div>
        <div className="hm-footer-col">
          <h4>Docs</h4>
          <Link to="/docs/getting-started/installation">Getting Started</Link>
          <Link to="/docs/concepts/swarm">Concepts</Link>
          <Link to="/docs/cli/overview">CLI Reference</Link>
          <Link to="/docs/plugins/overview">Plugins</Link>
        </div>
        <div className="hm-footer-col">
          <h4>Registry</h4>
          <Link to="https://registry.hivemind.rithul.dev">Browse</Link>
          <Link to="/docs/registry/publishing">Publish</Link>
          <Link to="/docs/registry/api-reference">API Reference</Link>
        </div>
      </div>
      <div className="hm-footer-bottom">
        Built by{' '}
        <a href="https://rithul.dev" target="_blank" rel="noopener noreferrer">
          rithul
        </a>{' '}
        &middot; MIT License
      </div>
    </footer>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */
export default function Home() {
  return (
    <Layout
      title="hivemind — The AI swarm runtime for complex tasks"
      description="hivemind breaks any task into a DAG of agents, runs them in parallel, and synthesizes the results."
      noFooter
    >
      <main className="hm-landing">
        <Hero />
        <FeatureGrid />
        <CodeTabs />
        <RegistryCallout />
        <Footer />
      </main>
    </Layout>
  );
}
