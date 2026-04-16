use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Intermediate representation of a compiled workflow
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowIr {
    pub name: String,
    pub version: Option<String>,
    pub model: String,
    pub workers: usize,
    pub bus: String,
    pub evolution: EvolutionIr,
    pub tasks: Vec<TaskIr>,
    pub plugins: Vec<PluginRef>,
    pub inputs: HashMap<String, InputIr>,
}

impl Default for WorkflowIr {
    fn default() -> Self {
        Self {
            name: "unnamed".to_string(),
            version: None,
            model: "claude-sonnet-4-6".to_string(),
            workers: 4,
            bus: "memory".to_string(),
            evolution: EvolutionIr::default(),
            tasks: vec![],
            plugins: vec![],
            inputs: HashMap::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvolutionIr {
    pub allow_mutations: bool,
    pub max_depth: u32,
    pub speculative: bool,
}

impl Default for EvolutionIr {
    fn default() -> Self {
        Self {
            allow_mutations: true,
            max_depth: 10,
            speculative: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskIr {
    pub id: String,
    pub prompt: String,
    pub model: Option<String>,
    pub can_mutate: bool,
    pub depends_on: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginRef {
    pub name: String,
    pub source: String, // "builtin:git", "./plugins/foo.devsper", "registry/foo@1.0"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InputIr {
    pub input_type: String,
    pub required: bool,
    pub default: Option<String>,
}
