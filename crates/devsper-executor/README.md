# devsper-executor

Parallel task executor for the devsper runtime. Drives a DAG to completion by repeatedly polling for ready nodes, claiming them, running agent functions concurrently, and writing results back.

## How it works

```
Executor::run(graph_handle, agent_fn)
  loop:
    ready_nodes = scheduler.get_ready()
    for each node (in parallel, up to concurrency limit):
      if scheduler.claim(node):
        result = agent_fn(node).await
        scheduler.complete(node, result)
    if no nodes remain: break
```

The executor is intentionally thin — it doesn't know about LLMs, memory, or plugins. Those concerns belong in the `agent_fn` you provide.

## Usage

```toml
[dependencies]
devsper-executor = "0.1"
```

```rust
use devsper_executor::{Executor, ExecutorConfig, AgentFn};
use devsper_graph::GraphHandle;
use devsper_core::NodeId;
use serde_json::json;

let config = ExecutorConfig { concurrency: 4, ..Default::default() };
let executor = Executor::new(config);

let agent: AgentFn = Arc::new(|node_id: NodeId, inputs: serde_json::Value| {
    Box::pin(async move {
        // call your LLM / tool here
        Ok(json!({ "result": "done" }))
    })
});

executor.run(graph_handle, agent).await?;
```

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
