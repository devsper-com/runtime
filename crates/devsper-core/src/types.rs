use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

/// Unique identifier for a workflow run
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RunId(pub String);

impl RunId {
    pub fn new() -> Self {
        Self(Uuid::new_v4().to_string())
    }
}

impl std::fmt::Display for RunId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl Default for RunId {
    fn default() -> Self {
        Self::new()
    }
}

/// Unique identifier for a graph node (task)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct NodeId(pub String);

impl NodeId {
    pub fn new() -> Self {
        Self(Uuid::new_v4().to_string())
    }

    pub fn from_label(s: &str) -> Self {
        Self(s.to_string())
    }
}

impl std::str::FromStr for NodeId {
    type Err = std::convert::Infallible;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Ok(Self(s.to_string()))
    }
}

impl std::fmt::Display for NodeId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl Default for NodeId {
    fn default() -> Self {
        Self::new()
    }
}

/// The current execution state of a graph node
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum NodeStatus {
    Pending,
    Ready,
    Running,
    Completed,
    Failed,
    Abandoned,
    Speculative,
}

/// Specification for a graph node (task)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeSpec {
    pub id: NodeId,
    pub prompt: String,
    pub model: Option<String>,
    pub can_mutate: bool,
    pub depends_on: Vec<NodeId>,
    pub metadata: HashMap<String, serde_json::Value>,
}

impl NodeSpec {
    pub fn new(prompt: impl Into<String>) -> Self {
        Self {
            id: NodeId::new(),
            prompt: prompt.into(),
            model: None,
            can_mutate: false,
            depends_on: vec![],
            metadata: HashMap::new(),
        }
    }

    pub fn with_id(mut self, id: NodeId) -> Self {
        self.id = id;
        self
    }

    pub fn with_model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    pub fn can_mutate(mut self) -> Self {
        self.can_mutate = true;
        self
    }

    pub fn depends_on(mut self, deps: Vec<NodeId>) -> Self {
        self.depends_on = deps;
        self
    }
}

/// A graph node with its current state
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub spec: NodeSpec,
    pub status: NodeStatus,
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
    pub started_at: Option<u64>,
    pub completed_at: Option<u64>,
}

impl Node {
    pub fn new(spec: NodeSpec) -> Self {
        Self {
            spec,
            status: NodeStatus::Pending,
            result: None,
            error: None,
            started_at: None,
            completed_at: None,
        }
    }

    pub fn id(&self) -> &NodeId {
        &self.spec.id
    }

    pub fn is_terminal(&self) -> bool {
        matches!(
            self.status,
            NodeStatus::Completed | NodeStatus::Failed | NodeStatus::Abandoned
        )
    }
}

/// A mutation that can be applied to a running graph
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GraphMutation {
    AddNode { spec: NodeSpec },
    AddEdge { from: NodeId, to: NodeId },
    RemoveEdge { from: NodeId, to: NodeId },
    SplitNode { node: NodeId, into: Vec<NodeSpec> },
    InjectBefore { before: NodeId, insert: NodeSpec },
    PruneSubgraph { root: NodeId },
    MarkSpeculative { nodes: Vec<NodeId> },
    ConfirmSpeculative { nodes: Vec<NodeId> },
    DiscardSpeculative { nodes: Vec<NodeId> },
}

/// A snapshot of the full graph state for checkpoint/recovery
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphSnapshot {
    pub run_id: RunId,
    pub nodes: HashMap<NodeId, Node>,
    pub edges: Vec<(NodeId, NodeId)>,
    pub event_count: u64,
    pub snapshot_at: u64,
}

/// An LLM generation request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmRequest {
    pub model: String,
    pub messages: Vec<LlmMessage>,
    pub tools: Vec<ToolDef>,
    pub max_tokens: Option<u32>,
    pub temperature: Option<f32>,
    pub system: Option<String>,
}

/// A message in an LLM conversation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmMessage {
    pub role: LlmRole,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum LlmRole {
    System,
    User,
    Assistant,
    Tool,
}

/// An LLM generation response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmResponse {
    pub content: String,
    pub tool_calls: Vec<ToolCall>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub model: String,
    pub stop_reason: StopReason,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum StopReason {
    EndTurn,
    ToolUse,
    MaxTokens,
    StopSequence,
}

/// Definition of a tool available to an agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDef {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value, // JSON Schema
}

/// A tool call requested by an LLM
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: serde_json::Value,
}

/// The result of executing a tool call
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub tool_call_id: String,
    pub content: serde_json::Value,
    pub is_error: bool,
}

/// A message on the event bus
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BusMessage {
    pub id: String,
    pub run_id: RunId,
    pub topic: String,
    pub payload: serde_json::Value,
    pub timestamp: u64,
}

impl BusMessage {
    pub fn new(run_id: RunId, topic: impl Into<String>, payload: serde_json::Value) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            run_id,
            topic: topic.into(),
            payload,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
        }
    }
}

/// Configuration for a workflow run
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeConfig {
    pub run_id: RunId,
    pub model: String,
    pub workers: usize,
    pub bus: BusConfig,
    pub evolution: EvolutionConfig,
}

impl Default for RuntimeConfig {
    fn default() -> Self {
        Self {
            run_id: RunId::new(),
            model: "claude-sonnet-4-6".to_string(),
            workers: 4,
            bus: BusConfig::Memory,
            evolution: EvolutionConfig::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum BusConfig {
    Memory,
    Redis { url: String },
    Kafka { brokers: Vec<String>, group_id: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvolutionConfig {
    pub allow_mutations: bool,
    pub max_depth: u32,
    pub speculative: bool,
}

impl Default for EvolutionConfig {
    fn default() -> Self {
        Self {
            allow_mutations: true,
            max_depth: 10,
            speculative: false,
        }
    }
}

/// A token streamed from an LLM
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Token {
    pub text: String,
    pub is_final: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RunState {
    Created,
    Running,
    WaitingHITL,
    Completed,
    Failed,
}

impl RunState {
    pub fn transition(&self, to: &RunState) -> Result<RunState, String> {
        use RunState::*;
        match (self, to) {
            (Created, Running) => Ok(to.clone()),
            (Running, WaitingHITL) => Ok(to.clone()),
            (Running, Completed) => Ok(to.clone()),
            (Running, Failed) => Ok(to.clone()),
            (WaitingHITL, Running) => Ok(to.clone()),
            (WaitingHITL, Failed) => Ok(to.clone()),
            _ => Err(format!("invalid transition {:?} → {:?}", self, to)),
        }
    }
}

impl Default for RunState {
    fn default() -> Self { RunState::Created }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum MemoryScope {
    Run,
    Context,
    Workflow,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_id_roundtrip() {
        let id = RunId::new();
        let json = serde_json::to_string(&id).unwrap();
        let id2: RunId = serde_json::from_str(&json).unwrap();
        assert_eq!(id, id2);
    }

    #[test]
    fn node_id_roundtrip() {
        let id = NodeId::new();
        let json = serde_json::to_string(&id).unwrap();
        let id2: NodeId = serde_json::from_str(&json).unwrap();
        assert_eq!(id, id2);
    }

    #[test]
    fn node_spec_builder() {
        let spec = NodeSpec::new("test task")
            .with_model("claude-sonnet-4-6")
            .can_mutate();
        assert_eq!(spec.prompt, "test task");
        assert!(spec.model.is_some());
        assert!(spec.can_mutate);
    }

    #[test]
    fn node_is_not_terminal_when_pending() {
        let spec = NodeSpec::new("test");
        let node = Node::new(spec);
        assert!(!node.is_terminal());
    }

    #[test]
    fn bus_message_has_timestamp() {
        let msg = BusMessage::new(RunId::new(), "test.topic", serde_json::json!({"key": "val"}));
        assert!(msg.timestamp > 0);
        assert!(!msg.id.is_empty());
    }

    #[test]
    fn node_terminal_states() {
        let make_node = |status: NodeStatus| {
            let mut node = Node::new(NodeSpec::new("test"));
            node.status = status;
            node
        };
        assert!(make_node(NodeStatus::Completed).is_terminal());
        assert!(make_node(NodeStatus::Failed).is_terminal());
        assert!(make_node(NodeStatus::Abandoned).is_terminal());
        assert!(!make_node(NodeStatus::Running).is_terminal());
        assert!(!make_node(NodeStatus::Ready).is_terminal());
        assert!(!make_node(NodeStatus::Speculative).is_terminal());
    }

    #[test]
    fn graph_mutation_serializes() {
        let m = GraphMutation::AddNode {
            spec: NodeSpec::new("a task"),
        };
        let json = serde_json::to_string(&m).unwrap();
        let m2: GraphMutation = serde_json::from_str(&json).unwrap();
        match m2 {
            GraphMutation::AddNode { spec } => assert_eq!(spec.prompt, "a task"),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn run_state_valid_transitions() {
        use RunState::*;
        assert!(Created.transition(&Running).is_ok());
        assert!(Running.transition(&Completed).is_ok());
        assert!(Running.transition(&WaitingHITL).is_ok());
        assert!(WaitingHITL.transition(&Running).is_ok());
        assert!(WaitingHITL.transition(&Failed).is_ok());
        assert!(Running.transition(&Failed).is_ok());
    }

    #[test]
    fn run_state_invalid_transitions() {
        use RunState::*;
        assert!(Created.transition(&Completed).is_err());
        assert!(Completed.transition(&Running).is_err());
        assert!(Failed.transition(&Running).is_err());
        assert!(Created.transition(&WaitingHITL).is_err());
    }

    #[test]
    fn memory_scope_variants_serialize() {
        for scope in [MemoryScope::Run, MemoryScope::Context, MemoryScope::Workflow] {
            let json = serde_json::to_string(&scope).unwrap();
            let back: MemoryScope = serde_json::from_str(&json).unwrap();
            assert_eq!(back, scope);
        }
    }
}
