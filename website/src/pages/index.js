import React from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';

export default function Home() {
  return (
    <Layout title="Hivemind" description="Distributed AI Swarm Runtime">
      <main className="hero">
        <div className="container">
          <h1 className="hero__title">Hivemind</h1>
          <p className="hero__subtitle">Distributed AI Swarm Runtime</p>
          <p className="hero__tagline">
            Orchestrate multi-agent systems with a swarm execution model: tasks to DAG to parallel execution.
          </p>
          <div className="hero__install">
            <code>pip install hivemind-ai</code>
            <span className="hero__cli">CLI: hivemind</span>
          </div>
          <div className="hero__links">
            <Link to="/docs/introduction" className="button button--primary button--lg">
              Introduction
            </Link>
            <Link to="/docs/configuration" className="button button--secondary button--lg">
              Configuration
            </Link>
            <Link to="/docs/cli" className="button button--secondary button--lg">
              CLI Reference
            </Link>
          </div>
        </div>
      </main>
    </Layout>
  );
}
