import React, { useState, useEffect } from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import { motion } from 'framer-motion';
import { ArrowRight, BookOpen, Settings, Terminal, Layers, Copy, Check } from 'lucide-react';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] },
  },
};

function AnimatedTerminal() {
  const [lines, setLines] = useState([]);

  useEffect(() => {
    const sequence = [
      { text: "$ uv run hivemind run \"List files in /tmp and summarize what you see\"", type: "prompt", delay: 500 },
      { text: "  Running…                                                              ", type: "dim", delay: 1200 },
      { text: "--- aadd3120 ---", type: "dim", delay: 1800 },
      { text: "Tool result (repo_structure_map):", type: "text", delay: 2000 },
      { text: "/", type: "tree", delay: 2100 },
      { text: "├── .hivemind", type: "tree", delay: 2150 },
      { text: "│   ├── events", type: "tree", delay: 2200 },
      { text: "│   │   ├── events_2026-03-10_dag.json", type: "tree", delay: 2300 },
      { text: "│   ├── memory.db", type: "tree", delay: 2400 },
      { text: "│   └── tool_analytics.db", type: "tree", delay: 2450 },
      { text: "├── logo.svg", type: "tree", delay: 2500 },
      { text: "└── logo_dark.svg", type: "tree", delay: 2550 },
      { text: "--- c858617b ---", type: "dim", delay: 3000 },
      { text: "Tool result (run_shell_command):", type: "text", delay: 3200 },
      { text: "NAME|SIZE|TYPE|PERMS|OWNER|MTIME", type: "text", delay: 3400 },
      { text: "2f093fe9-a235-5d1c-9a62-3fae2cdf7eb1|-|unknown|-|-|-", type: "text", delay: 3450 },
      { text: "Arturia|-|unknown|-|-|-", type: "text", delay: 3500 },
      { text: "hivemind_build_out|-|unknown|-|-|-", type: "text", delay: 3550 },
      { text: "test_refs.docx|-|unknown|-|-|-", type: "text", delay: 3600 },
      { text: "$", type: "prompt", delay: 4500 }
    ];

    let timeouts = [];
    sequence.forEach((line) => {
      const timeout = setTimeout(() => {
        setLines(prev => [...prev, line]);
      }, line.delay);
      timeouts.push(timeout);
    });

    return () => timeouts.forEach(clearTimeout);
  }, []);

  const bodyRef = React.useRef(null);
  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [lines]);

  return (
    <div className="hero-terminal">
      <div className="hero-terminal-header">
        <div className="hero-terminal-dot red" />
        <div className="hero-terminal-dot yellow" />
        <div className="hero-terminal-dot green" />
      </div>
      <div ref={bodyRef} className="hero-terminal-body hero-terminal-body-scroll">
        {lines.map((line, i) => (
          <motion.div
            key={i}
            className="term-line"
            style={{ flexDirection: line.type === 'prompt' && line.text.startsWith('$') ? 'column' : 'row' }}
            initial={{ opacity: 0, x: -5 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.1 }}
          >
            {line.type === 'prompt' && line.text.startsWith('$') ? (
              <>
                <span className="term-prompt" style={{ marginBottom: '4px' }}>~/dev/hivemind/ on main!</span>
                <div style={{ display: 'flex' }}>
                  <span className="term-prompt">$</span>
                  <span className="term-text">{line.text.slice(2)}</span>
                </div>
              </>
            ) : (
              <span className={`term-${line.type}`}>{line.text}</span>
            )}
          </motion.div>
        ))}
        {/* Blinking cursor */}
        {lines.length < 23 && (
          <motion.div
            className="term-line"
            animate={{ opacity: [1, 0] }}
            transition={{ repeat: Infinity, duration: 0.8 }}
          >
            <span className="term-text">_</span>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function CodeSnippet() {
  const [copied, setCopied] = useState(false);
  const code = "pip install hivemind-ai";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy', err);
    }
  };

  return (
    <div className="hero-code-wrapper" onClick={handleCopy}>
      <div className="hero-install-premium">
        <span>$ {code}</span>
        <div className="copy-icon">
          {copied ? <Check size={16} className="term-success" /> : <Copy size={16} />}
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <Layout title="Hivemind" description="Distributed AI Swarm Runtime" noFooter>
      <motion.main
        className="landing-page"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <div className="landing-split">
          <div className="landing-left">
            <motion.div variants={itemVariants}>
              <Link to="/docs/release_notes" className="hero-pill">
                <span className="hero-pill-icon">✨</span>
                <span>What's new in v2.1.5 — Release notes</span>
                <ArrowRight size={14} className="hero-pill-icon" style={{ color: '#a8b1ff', marginLeft: '4px' }} />
              </Link>
            </motion.div>

            <motion.div className="hero-wordmark" variants={itemVariants}>
              Hivemind
            </motion.div>

            <motion.h1 className="hero-headline" variants={itemVariants}>
              Distributed AI Swarm Runtime
            </motion.h1>

            <motion.p className="hero-description" variants={itemVariants}>
              Orchestrate multi-agent systems with a swarm execution model: tasks become a DAG, then run in parallel across isolated nodes.
            </motion.p>

            <motion.div variants={itemVariants}>
              <CodeSnippet />
            </motion.div>
          </div>

          <div className="landing-right">
            <motion.div variants={itemVariants} style={{ width: '100%' }}>
              <AnimatedTerminal />
            </motion.div>
          </div>
        </div>

        <motion.div className="bento-grid" variants={itemVariants}>
          <Link to="/docs/introduction" className="bento-card">
            <div className="bento-icon"><BookOpen size={20} /></div>
            <div>
              <h3 className="bento-title">Introduction</h3>
              <p className="bento-desc">Learn the core concepts of Swarm intelligence and DAG-based task routing.</p>
            </div>
          </Link>

          <Link to="/docs/configuration" className="bento-card">
            <div className="bento-icon"><Settings size={20} /></div>
            <div>
              <h3 className="bento-title">Configuration</h3>
              <p className="bento-desc">Configure your distributed nodes, resource limits, and environment variables.</p>
            </div>
          </Link>

          <Link to="/docs/cli" className="bento-card">
            <div className="bento-icon"><Terminal size={20} /></div>
            <div>
              <h3 className="bento-title">CLI Reference</h3>
              <p className="bento-desc">Explore commands to initialize, manage, and monitor your AI swarms.</p>
            </div>
          </Link>

          <Link to="/docs/architecture" className="bento-card">
            <div className="bento-icon"><Layers size={20} /></div>
            <div>
              <h3 className="bento-title">Architecture</h3>
              <p className="bento-desc">Deep dive into the runtime execution model and orchestration layer.</p>
            </div>
          </Link>
        </motion.div>
      </motion.main>
    </Layout>
  );
}
