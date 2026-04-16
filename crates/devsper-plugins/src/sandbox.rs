use std::path::{Path, PathBuf};

/// Sandbox configuration for a plugin
#[derive(Debug, Clone)]
pub struct Sandbox {
    /// Workspace root — all file ops restricted here
    pub workspace: PathBuf,
    /// Whether plugin can run arbitrary subprocesses
    pub allow_exec: bool,
    /// Whether plugin can make HTTP requests
    pub allow_http: bool,
}

impl Sandbox {
    pub fn new(workspace: impl Into<PathBuf>) -> Self {
        Self {
            workspace: workspace.into(),
            allow_exec: true,
            allow_http: true,
        }
    }

    /// Check if a path is within the sandbox workspace
    pub fn is_allowed_path(&self, path: &Path) -> bool {
        path.starts_with(&self.workspace)
    }
}
