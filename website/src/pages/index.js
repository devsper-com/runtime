import React, { useState, useEffect, useRef } from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import CodeBlock from '@theme/CodeBlock';
import { motion, useInView, AnimatePresence } from 'framer-motion';

/* ------------------------------------------------------------------ */
/*  Animation variants                                                 */
/* ------------------------------------------------------------------ */
const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: i * 0.1 },
  }),
};

const stagger = {
  visible: { transition: { staggerChildren: 0.08 } },
};

const cardVariant = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
  },
};

/* ------------------------------------------------------------------ */
/*  Section 1 — Hero                                                   */
/* ------------------------------------------------------------------ */
const terminalText =
  '$ devsper run "Research the top 5 AI papers this week,\n' +
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
    <motion.div
      className="hero-terminal"
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.7, delay: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
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
    </motion.div>
  );
}

function Hero() {
  return (
    <section className="hm-hero">
      {/* Ambient lighting layers */}
      <div className="hm-hero-grid" aria-hidden="true" />
      <div className="hm-hero-ambient-1" aria-hidden="true" />
      <div className="hm-hero-ambient-2" aria-hidden="true" />
      <div className="hm-hero-ambient-3" aria-hidden="true" />

      <div className="hm-hero-inner">
        <div className="hm-hero-content">
          <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={1}>
            <Link to="/docs/changelog" className="hm-badge">
              v2.1.6 &mdash; Plugin registry live &rarr;
            </Link>
          </motion.div>

          <motion.h1
            className="hm-hero-h1"
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            custom={0}
          >
            The AI swarm runtime<br />for complex tasks
          </motion.h1>

          <motion.p
            className="hm-hero-sub"
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            custom={2}
          >
            devsper breaks any task into a DAG of agents,
            runs them in parallel, and synthesizes the results.
          </motion.p>

          <motion.div
            className="hm-hero-ctas"
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            custom={2}
          >
            <Link
              to="/docs/getting-started/installation"
              className="hm-btn hm-btn-primary"
            >
              Get started
            </Link>
            <Link
              to="https://github.com/devsper-com/runtime"
              className="hm-btn hm-btn-ghost"
            >
              View on GitHub
            </Link>
          </motion.div>

          <motion.div
            className="hm-hero-terminal-wrap"
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            custom={3}
          >
            <HeroTerminal />
          </motion.div>
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
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.15 });

  return (
    <section ref={ref} className="hm-features">
      <motion.h2
        className="hm-section-heading"
        variants={fadeUp}
        initial="hidden"
        animate={inView ? 'visible' : 'hidden'}
        custom={0}
      >
        Everything you need to build with AI agents
      </motion.h2>
      <motion.p
        className="hm-section-subheading"
        variants={fadeUp}
        initial="hidden"
        animate={inView ? 'visible' : 'hidden'}
        custom={1}
      >
        Built for production. Designed for developers.
      </motion.p>
      <motion.div
        className="hm-feature-grid"
        variants={stagger}
        initial="hidden"
        animate={inView ? 'visible' : 'hidden'}
      >
        {features.map((f) => (
          <motion.div key={f.title} className="hm-feature-card" variants={cardVariant}>
            <span className="hm-feature-icon">{f.icon}</span>
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 3 — Code example tabs (with Prism syntax highlighting)     */
/* ------------------------------------------------------------------ */
const codeTabs = [
  {
    id: 'run',
    label: 'Run a task',
    lang: 'python',
    code: `import devsper

result = devsper.run(
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
    code: `from devsper.tools.base import Tool
from devsper.tools.registry import register

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
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.15 });

  const activeTab = codeTabs.find((t) => t.id === active);

  return (
    <motion.section
      ref={ref}
      className="hm-code-section"
      variants={fadeUp}
      initial="hidden"
      animate={inView ? 'visible' : 'hidden'}
      custom={0}
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
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="hm-code-block-wrap"
            >
              <CodeBlock language={activeTab.lang}>
                {activeTab.code}
              </CodeBlock>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </motion.section>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 4 — Registry callout                                       */
/* ------------------------------------------------------------------ */
function RegistryCallout() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.15 });

  return (
    <motion.section
      ref={ref}
      className="hm-registry"
      variants={fadeUp}
      initial="hidden"
      animate={inView ? 'visible' : 'hidden'}
      custom={0}
    >
      <div className="hm-registry-card">
        <div className="hm-registry-text">
          <h2>Share tools with the ecosystem</h2>
          <p>
            Publish plugins to the devsper registry. One command to install,
            one command to publish. pip-compatible.
          </p>
          <div className="hm-registry-links">
            <Link to="https://registry.devsper.com" className="hm-link-arrow">
              Browse registry &rarr;
            </Link>
            <Link to="/docs/plugins/publishing" className="hm-link-arrow">
              Publish your first plugin &rarr;
            </Link>
          </div>
        </div>
        <div className="hm-registry-terminal">
          <motion.div
            className="hero-terminal"
            initial={{ opacity: 0, x: 20 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="hero-terminal-header">
              <span className="hero-terminal-dot red" />
              <span className="hero-terminal-dot yellow" />
              <span className="hero-terminal-dot green" />
            </div>
            <div className="hero-terminal-body">
              <div className="term-line term-prompt">
                $ devsper reg install devsper-plugin-browseruse
              </div>
              <div className="term-line term-success">
                {'\u2713'} Installed 3 tools: browse, click, extract_text
              </div>
              <div className="term-line" />
              <div className="term-line term-prompt">
                $ devsper run "Book me a flight to Tokyo next Friday"
              </div>
              <div className="term-line term-dim">
                {'\u28FE'} Planning...
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </motion.section>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 5 — Footer                                                 */
/* ------------------------------------------------------------------ */
function Footer() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.1 });

  return (
    <motion.footer
      ref={ref}
      className="hm-footer"
      variants={fadeUp}
      initial="hidden"
      animate={inView ? 'visible' : 'hidden'}
      custom={0}
    >
      <div className="hm-footer-inner">
        <div className="hm-footer-col hm-footer-brand">
          <h4>devsper</h4>
          <p>The AI swarm runtime for complex tasks.</p>
          <Link to="https://github.com/devsper-com/runtime">
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
          <Link to="https://registry.devsper.com">Browse</Link>
          <Link to="/docs/registry/publishing">Publish</Link>
          <Link to="/docs/registry/api-reference">API Reference</Link>
        </div>
      </div>
      <div className="hm-footer-bottom">
        Built by{' '}
        <a href="https://rithul.dev" target="_blank" rel="noopener noreferrer">
          rithul
        </a>{' '}
        &middot; GPL-3.0 License
      </div>
    </motion.footer>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */
export default function Home() {
  return (
    <Layout
      title="devsper — The AI swarm runtime for complex tasks"
      description="devsper breaks any task into a DAG of agents, runs them in parallel, and synthesizes the results."
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
