//! PyExternalMemory — Python-backed MemoryStore for callback injection.
//!
//! Python constructs a `VektoriMemoryBridge` and passes it to Rust.
//! Rust wraps it in a `#[pyclass]` and implements `MemoryStore` by calling
//! back into the Python object's methods via PyO3.

use anyhow::{anyhow, Result};
use devsper_core::{MemoryHit, MemoryStore};
use pyo3::prelude::*;
use pyo3::types::PyTuple;

use serde_json::Value;
use std::sync::Arc;

/// A Python object that provides memory operations via callback.
///
/// Python constructs this by passing a `VektoriMemoryBridge` instance:
/// ```python
/// from devsper._vektori_bridge import VektoriMemoryBridge
/// bridge = VektoriMemoryBridge(database_url="...")
/// # Then pass bridge to run_workflow(memory=bridge)
/// ```
///
/// Rust calls `bridge.store()`, `bridge.search()`, etc. via PyO3.
#[pyclass(name = "ExternalMemory")]
pub struct PyExternalMemory {
    /// Reference to the Python memory bridge object.
    inner: Py<PyAny>,
}

#[pymethods]
impl PyExternalMemory {
    #[new]
    fn new(obj: Py<PyAny>) -> PyResult<Self> {
        // Validate that the Python object has the required methods
        Python::with_gil(|py| {
            let bound = obj.bind(py);
            for method in &["store", "retrieve", "search", "delete", "health"] {
                if !bound.hasattr(*method)? {
                    return Err(pyo3::exceptions::PyTypeError::new_err(format!(
                        "Python memory object must have a '{}' method",
                        method
                    )));
                }
            }
            Ok(())
        })?;

        Ok(Self { inner: obj })
    }
}

impl PyExternalMemory {
    /// Call a method on the Python bridge object, returning a String.
    fn call_method_str(
        &self,
        py: Python<'_>,
        method: &str,
        args: impl IntoPy<Py<PyTuple>>,
    ) -> Result<String> {
        let bound = self.inner.bind(py);
        let result = bound
            .call_method1(method, args)
            .map_err(|e| anyhow!("Python memory bridge '{}' failed: {}", method, e))?;

        // Handle None return
        if result.is_none() {
            return Ok(String::new());
        }

        result.extract::<String>().map_err(|e| {
            anyhow!(
                "Python memory bridge '{}' returned non-string: {}",
                method,
                e
            )
        })
    }

    /// Call a method that returns Option<String> (may return None).
    fn call_method_optional_str(
        &self,
        py: Python<'_>,
        method: &str,
        args: impl IntoPy<Py<PyTuple>>,
    ) -> Result<Option<String>> {
        let bound = self.inner.bind(py);
        let result = bound
            .call_method1(method, args)
            .map_err(|e| anyhow!("Python memory bridge '{}' failed: {}", method, e))?;

        if result.is_none() {
            return Ok(None);
        }

        result.extract::<Option<String>>().map_err(|e| {
            anyhow!(
                "Python memory bridge '{}' returned unexpected type: {}",
                method,
                e
            )
        })
    }

    /// Call a void method (no meaningful return).
    fn call_method_void(
        &self,
        py: Python<'_>,
        method: &str,
        args: impl IntoPy<Py<PyTuple>>,
    ) -> Result<()> {
        let bound = self.inner.bind(py);
        bound
            .call_method1(method, args)
            .map_err(|e| anyhow!("Python memory bridge '{}' failed: {}", method, e))?;
        Ok(())
    }
}

#[async_trait::async_trait]
impl MemoryStore for PyExternalMemory {
    async fn store(&self, namespace: &str, key: &str, value: Value) -> Result<()> {
        let ns = namespace.to_string();
        let k = key.to_string();
        let v = value.to_string();

        // Acquire the GIL. Safe in async contexts as long as we don't hold
        // it across .await points (which we don't — the call is synchronous).
        Python::with_gil(|py| self.call_method_void(py, "store", (ns, k, v)))
    }

    async fn retrieve(&self, namespace: &str, key: &str) -> Result<Option<Value>> {
        let ns = namespace.to_string();
        let k = key.to_string();

        Python::with_gil(|py| {
            let result = self.call_method_optional_str(py, "retrieve", (ns, k))?;
            match result {
                Some(s) if !s.is_empty() => serde_json::from_str::<Value>(&s)
                    .map(Some)
                    .map_err(|e| anyhow!("Failed to parse retrieve result as JSON: {}", e)),
                _ => Ok(None),
            }
        })
    }

    async fn search(&self, namespace: &str, query: &str, top_k: usize) -> Result<Vec<MemoryHit>> {
        let ns = namespace.to_string();
        let q = query.to_string();
        let k = top_k as i64;

        Python::with_gil(|py| {
            let result_str = self.call_method_str(py, "search", (ns, q, k))?;
            if result_str.is_empty() || result_str == "[]" {
                return Ok(vec![]);
            }

            // Parse the JSON array of hits from Python
            let raw_hits: Vec<serde_json::Value> = serde_json::from_str(&result_str)
                .map_err(|e| anyhow!("Failed to parse search results as JSON: {}", e))?;

            let mut hits = Vec::with_capacity(raw_hits.len());
            for raw in raw_hits {
                let key = raw
                    .get("key")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                let value = raw.get("value").cloned().unwrap_or(Value::Null);
                let score = raw.get("score").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
                hits.push(MemoryHit { key, value, score });
            }
            Ok(hits)
        })
    }

    async fn delete(&self, namespace: &str, key: &str) -> Result<()> {
        let ns = namespace.to_string();
        let k = key.to_string();

        Python::with_gil(|py| self.call_method_void(py, "delete", (ns, k)))
    }
}

/// Wrap a PyExternalMemory in an `Arc<dyn MemoryStore>` for use with MemoryRouter.
///
/// Validates that the Python object has the required methods before wrapping.
pub fn wrap_memory_store(py_mem: Py<PyAny>) -> Result<Arc<dyn MemoryStore>> {
    // Validate it has the right methods
    Python::with_gil(|py| {
        let bound = py_mem.bind(py);
        for method in &["store", "retrieve", "search", "delete", "health"] {
            if !bound.hasattr(*method)? {
                return Err(anyhow!(
                    "Python memory object must have a '{}' method",
                    method
                ));
            }
        }
        Ok(())
    })?;

    let external = PyExternalMemory { inner: py_mem };
    Ok(Arc::new(external))
}
