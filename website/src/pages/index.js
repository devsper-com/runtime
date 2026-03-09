import React from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import { motion } from 'framer-motion';

const container = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.06,
      delayChildren: 0.08,
    },
  },
};

const item = {
  hidden: { opacity: 0, y: 6 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] },
  },
};

export default function Home() {
  return (
    <Layout title="Hivemind" description="Distributed AI Swarm Runtime" noFooter>
      <motion.main
        className="landing-page"
        variants={container}
        initial="hidden"
        animate="visible"
      >
        <motion.div className="hero-wordmark" variants={item}>
          Hivemind
        </motion.div>
        <motion.h1 className="hero-headline" variants={item}>
          Distributed AI Swarm Runtime
        </motion.h1>
        <motion.p className="hero-description" variants={item}>
          Orchestrate multi-agent systems with a swarm execution model: tasks to DAG to parallel execution.
        </motion.p>
        <motion.code className="hero-install" variants={item}>
          $ pip install hivemind-ai
        </motion.code>
        <motion.nav
          className="hero-links"
          aria-label="Quick links"
          variants={item}
        >
          <Link to="/docs/introduction">Introduction</Link>
          <Link to="/docs/configuration">Configuration</Link>
          <Link to="/docs/cli">CLI Reference</Link>
        </motion.nav>
      </motion.main>
    </Layout>
  );
}
