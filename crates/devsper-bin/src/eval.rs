//! Eval commands — batch-run a workflow against a dataset and report results.

use std::path::PathBuf;
use std::time::Instant;

/// Run a workflow against a JSONL dataset, writing results to an output JSONL file.
pub async fn eval_run(workflow: PathBuf, dataset: PathBuf, output: PathBuf) -> anyhow::Result<()> {
    use std::io::{BufRead, Write};

    let dataset_file = std::fs::File::open(&dataset)
        .map_err(|e| anyhow::anyhow!("Cannot open dataset '{}': {e}", dataset.display()))?;

    let mut output_file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&output)
        .map_err(|e| anyhow::anyhow!("Cannot open output '{}': {e}", output.display()))?;

    let exe = std::env::current_exe()?;
    let reader = std::io::BufReader::new(dataset_file);
    let mut total = 0usize;
    let mut succeeded = 0usize;

    for (i, line) in reader.lines().enumerate() {
        let line = line?;
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        let raw: serde_json::Value = serde_json::from_str(line)
            .map_err(|e| anyhow::anyhow!("Line {}: invalid JSON: {e}", i + 1))?;

        // Normalize input format
        let inputs = normalize_inputs(&raw);

        // Build CLI args: run <workflow> --input k=v ...
        let mut args = vec![
            "run".to_string(),
            workflow.to_string_lossy().into_owned(),
        ];
        for (k, v) in inputs.as_object().unwrap_or(&serde_json::Map::new()) {
            let v_str = match v {
                serde_json::Value::String(s) => s.clone(),
                other => other.to_string(),
            };
            args.push("--input".to_string());
            args.push(format!("{k}={v_str}"));
        }

        print!("  Case {}: ", i + 1);
        std::io::stdout().flush().ok();

        let start = Instant::now();
        let child = std::process::Command::new(&exe)
            .args(&args)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn();

        let (exit_code, stdout_str, stderr_str) = match child {
            Ok(c) => {
                let out = c.wait_with_output()?;
                let code = out.status.code().unwrap_or(-1);
                let stdout = String::from_utf8_lossy(&out.stdout).into_owned();
                let stderr = String::from_utf8_lossy(&out.stderr).into_owned();
                (code, stdout, stderr)
            }
            Err(e) => (-1, String::new(), e.to_string()),
        };

        let latency_ms = start.elapsed().as_millis() as u64;
        let success = exit_code == 0;

        if success {
            succeeded += 1;
            println!("ok ({latency_ms}ms)");
        } else {
            println!("FAIL ({latency_ms}ms, exit={exit_code})");
            if !stderr_str.is_empty() {
                let preview: String = stderr_str.lines().next().unwrap_or("").chars().take(80).collect();
                println!("    stderr: {preview}");
            }
        }

        let result = serde_json::json!({
            "inputs": inputs,
            "output": stdout_str.trim(),
            "exit_code": exit_code,
            "latency_ms": latency_ms,
            "success": success,
            "stderr": stderr_str.trim(),
        });

        writeln!(output_file, "{}", serde_json::to_string(&result)?)?;
        total += 1;
    }

    println!();
    println!("Eval complete: {succeeded}/{total} passed");
    println!("Results written to: {}", output.display());
    Ok(())
}

/// Report summary of eval results from a JSONL file.
pub fn eval_report(input: PathBuf, last: usize) -> anyhow::Result<()> {
    use std::io::BufRead;

    let file = std::fs::File::open(&input)
        .map_err(|e| anyhow::anyhow!("Cannot open results '{}': {e}", input.display()))?;

    let reader = std::io::BufReader::new(file);
    let mut entries: Vec<serde_json::Value> = Vec::new();

    for line in reader.lines() {
        let line = line?;
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if let Ok(v) = serde_json::from_str(line) {
            entries.push(v);
        }
    }

    if last > 0 && entries.len() > last {
        let skip = entries.len() - last;
        entries = entries.into_iter().skip(skip).collect();
    }

    if entries.is_empty() {
        println!("No eval results found in '{}'", input.display());
        return Ok(());
    }

    let total = entries.len();
    let succeeded = entries.iter().filter(|e| e["success"].as_bool().unwrap_or(false)).count();
    let success_rate = (succeeded as f64 / total as f64) * 100.0;
    let avg_latency = if total > 0 {
        entries.iter().filter_map(|e| e["latency_ms"].as_u64()).sum::<u64>() / total as u64
    } else {
        0
    };

    println!("=== Eval Report ===");
    println!("  Total cases:   {total}");
    println!("  Success rate:  {succeeded}/{total} ({success_rate:.1}%)");
    println!("  Avg latency:   {avg_latency}ms");
    println!();

    // Per-case table
    let col_w = [30usize, 8, 12, 82];
    let sep = format!(
        "+-{:-<w0$}-+-{:-<w1$}-+-{:-<w2$}-+-{:-<w3$}-+",
        "", "", "", "",
        w0 = col_w[0], w1 = col_w[1], w2 = col_w[2], w3 = col_w[3],
    );
    println!("{sep}");
    println!(
        "| {:<w0$} | {:<w1$} | {:<w2$} | {:<w3$} |",
        "inputs", "success", "latency_ms", "output preview",
        w0 = col_w[0], w1 = col_w[1], w2 = col_w[2], w3 = col_w[3],
    );
    println!("{sep}");

    for entry in &entries {
        let inputs_str = match &entry["inputs"] {
            serde_json::Value::Object(m) => m
                .iter()
                .map(|(k, v)| {
                    let vs = match v {
                        serde_json::Value::String(s) => s.clone(),
                        other => other.to_string(),
                    };
                    format!("{k}={vs}")
                })
                .collect::<Vec<_>>()
                .join(", "),
            other => other.to_string(),
        };
        let inputs_display = truncate(&inputs_str, col_w[0]);
        let success = if entry["success"].as_bool().unwrap_or(false) { "yes" } else { "no" };
        let latency = entry["latency_ms"].as_u64().unwrap_or(0).to_string();
        let output_raw = entry["output"].as_str().unwrap_or("").replace('\n', " ");
        let output_preview = truncate(&output_raw, col_w[3]);

        println!(
            "| {:<w0$} | {:<w1$} | {:<w2$} | {:<w3$} |",
            inputs_display, success, latency, output_preview,
            w0 = col_w[0], w1 = col_w[1], w2 = col_w[2], w3 = col_w[3],
        );
    }
    println!("{sep}");
    Ok(())
}

/// Normalize dataset entry to `{"key": "value", ...}` inputs object.
fn normalize_inputs(raw: &serde_json::Value) -> serde_json::Value {
    // If {"inputs": {...}} — use inner object directly
    if let Some(inner) = raw.get("inputs") {
        if inner.is_object() {
            return inner.clone();
        }
    }
    // If {"input": "string"} — wrap as {"query": "string"}
    if let Some(input_str) = raw.get("input").and_then(|v| v.as_str()) {
        return serde_json::json!({ "query": input_str });
    }
    // Fallback: use the whole object as inputs
    raw.clone()
}

fn truncate(s: &str, max: usize) -> String {
    if s.len() <= max {
        s.to_string()
    } else {
        format!("{}...", &s[..max.saturating_sub(3)])
    }
}
