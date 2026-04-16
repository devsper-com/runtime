use crate::ir::WorkflowIr;
use anyhow::{anyhow, Result};
use std::path::Path;

/// Loads workflow IR from a .devsper source or .devsper.bin bytecode file
pub struct WorkflowLoader;

impl WorkflowLoader {
    /// Load from either source (.devsper) or compiled (.devsper.bin / JSON IR)
    pub fn load(path: &Path) -> Result<WorkflowIr> {
        let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");

        if name.ends_with(".devsper.bin") || ext == "bin" {
            Self::load_bytecode(path)
        } else {
            Self::load_source(path)
        }
    }

    fn load_bytecode(path: &Path) -> Result<WorkflowIr> {
        let bytes = std::fs::read(path)
            .map_err(|e| anyhow!("Cannot read {}: {e}", path.display()))?;
        serde_json::from_slice(&bytes)
            .map_err(|e| anyhow!("Invalid bytecode (JSON IR) in {}: {e}", path.display()))
    }

    fn load_source(path: &Path) -> Result<WorkflowIr> {
        use crate::compiler::{CompileOptions, Compiler};
        let compiler = Compiler::new(CompileOptions::default());
        compiler.parse_file(path)
    }
}
