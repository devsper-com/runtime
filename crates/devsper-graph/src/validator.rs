use devsper_core::{GraphMutation, NodeId};
use petgraph::algo::is_cyclic_directed;
use petgraph::graph::{DiGraph, NodeIndex};
use std::collections::HashMap;

/// Validates that graph mutations do not introduce cycles.
/// Uses petgraph's DFS-based cycle detection.
pub struct MutationValidator;

impl MutationValidator {
    pub fn new() -> Self {
        Self
    }

    /// Returns Ok(()) if mutation is safe, Err(reason) if it would create a cycle.
    pub fn validate(
        &self,
        graph: &DiGraph<NodeId, ()>,
        index_map: &HashMap<NodeId, NodeIndex>,
        mutation: &GraphMutation,
    ) -> Result<(), String> {
        match mutation {
            GraphMutation::AddEdge { from, to } => {
                self.validate_add_edge(graph, index_map, from, to)
            }
            // InjectBefore adds a new node (no incoming edges yet) with one outgoing edge → safe
            GraphMutation::InjectBefore { .. } => Ok(()),
            // SplitNode replaces an existing node with new ones — no new cycles possible
            GraphMutation::SplitNode { .. } => Ok(()),
            GraphMutation::RemoveNode { id } => {
                if !index_map.contains_key(id) {
                    Err(format!("Node not found: {id}"))
                } else {
                    Ok(())
                }
            }
            GraphMutation::ModifyNode { id, .. } => {
                if !index_map.contains_key(id) {
                    Err(format!("Node not found: {id}"))
                } else {
                    Ok(())
                }
            }
            // All other mutations don't add edges
            _ => Ok(()),
        }
    }

    fn validate_add_edge(
        &self,
        graph: &DiGraph<NodeId, ()>,
        index_map: &HashMap<NodeId, NodeIndex>,
        from: &NodeId,
        to: &NodeId,
    ) -> Result<(), String> {
        let from_idx = index_map
            .get(from)
            .copied()
            .ok_or_else(|| format!("Node not found: {from}"))?;
        let to_idx = index_map
            .get(to)
            .copied()
            .ok_or_else(|| format!("Node not found: {to}"))?;

        // Clone graph, add edge, check for cycle
        let mut test_graph = graph.clone();
        test_graph.add_edge(from_idx, to_idx, ());

        if is_cyclic_directed(&test_graph) {
            Err(format!("Edge {from} → {to} would create a cycle"))
        } else {
            Ok(())
        }
    }
}

impl Default for MutationValidator {
    fn default() -> Self {
        Self::new()
    }
}
