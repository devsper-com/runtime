use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::io::{self, Read};

#[derive(Debug, Deserialize)]
struct RankRequest {
    query_text: String,
    query_embedding: Option<Vec<f32>>,
    top_k: usize,
    min_similarity: f32,
    embed_weight: f32,
    candidates: Vec<Candidate>,
}

#[derive(Debug, Deserialize)]
struct Candidate {
    id: String,
    content: String,
    tags: Vec<String>,
    embedding: Option<Vec<f32>>,
    timestamp: Option<String>,
    memory_type: Option<String>,
    source_task: Option<String>,
}

#[derive(Debug, Serialize)]
struct Ranked {
    id: String,
    score: f32,
}

#[derive(Debug, Serialize)]
struct RankResponse {
    ranked: Vec<Ranked>,
}

#[derive(Debug, Deserialize)]
struct Injection {
    content: String,
    tags: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
struct FormatContextRequest {
    user_injections: Vec<Injection>,
    ranked_candidates: Vec<Candidate>,
}

#[derive(Debug, Serialize)]
struct FormatContextResponse {
    context: String,
}

fn truncate_chars(s: &str, max_chars: usize) -> String {
    let mut count = 0usize;
    let mut end_idx = 0usize;
    for (idx, _) in s.char_indices() {
        if count >= max_chars {
            end_idx = idx;
            break;
        }
        end_idx = idx;
        count += 1;
    }
    if s.chars().count() <= max_chars {
        s.to_string()
    } else {
        format!("{}...", s[..end_idx].to_string())
    }
}

fn token_set(s: &str, re: &Regex) -> HashSet<String> {
    re.find_iter(s)
        .map(|m| m.as_str().to_ascii_lowercase())
        .filter(|t| t.len() >= 2)
        .collect()
}

fn overlap_score(query_terms: &HashSet<String>, candidate_terms: &HashSet<String>) -> f32 {
    if query_terms.is_empty() || candidate_terms.is_empty() {
        return 0.0;
    }
    let mut matches = 0usize;
    for t in query_terms {
        if candidate_terms.contains(t) {
            matches += 1;
        }
    }
    matches as f32 / (query_terms.len() as f32)
}

fn signature_tokens(s: &str, re: &Regex, max_tokens: usize) -> String {
    let mut tokens: Vec<String> = re
        .find_iter(s)
        .map(|m| m.as_str().to_ascii_lowercase())
        .filter(|t| t.len() >= 2)
        .collect();
    tokens.sort_unstable();
    tokens.dedup();
    if tokens.len() > max_tokens {
        tokens.truncate(max_tokens);
    }
    tokens.join(" ")
}

fn cosine_sim(a: &[f32], b: &[f32]) -> f32 {
    if a.is_empty() || b.is_empty() || a.len() != b.len() {
        return 0.0;
    }
    let mut dot = 0.0f32;
    let mut na = 0.0f32;
    let mut nb = 0.0f32;
    for (x, y) in a.iter().zip(b.iter()) {
        dot += x * y;
        na += x * x;
        nb += y * y;
    }
    if na <= 0.0 || nb <= 0.0 {
        return 0.0;
    }
    let denom = (na.sqrt()) * (nb.sqrt());
    if denom == 0.0 {
        return 0.0;
    }
    let s = dot / denom;
    if !s.is_finite() {
        0.0
    } else {
        s
    }
}

fn parse_rfc3339_epoch_seconds(ts: &str) -> Option<i64> {
    // Timestamp comes from Python (`datetime.isoformat()`), typically RFC3339-ish.
    // We use the RFC3339 parser and fall back to None on failure.
    let dt = chrono::DateTime::parse_from_rfc3339(ts).ok()?;
    Some(dt.timestamp())
}

fn memory_type_weight(memory_type: Option<&str>) -> f32 {
    match memory_type.unwrap_or("").to_ascii_lowercase().as_str() {
        "research" => 1.15,
        "artifact" => 1.10,
        "semantic" => 1.05,
        "episodic" => 1.00,
        _ => 1.00,
    }
}

pub fn run_ranking() {
    let mut argv = std::env::args();
    let _bin = argv.next();
    let cmd = argv.next().unwrap_or_else(|| "rank".to_string());

    if cmd != "rank" {
        eprintln!("Unsupported command: {}", cmd);
        std::process::exit(2);
    }

    let mut input = String::new();
    if io::stdin().read_to_string(&mut input).is_err() {
        std::process::exit(2);
    }

    let token_re = Regex::new(r"\w+").expect("valid token regex");
    if cmd == "rank" {
        let req: RankRequest = match serde_json::from_str(&input) {
            Ok(v) => v,
            Err(e) => {
                eprintln!("Invalid JSON input: {e}");
                std::process::exit(2);
            }
        };

        let query_terms = token_set(&req.query_text, &token_re);
        let embed_weight = req.embed_weight.clamp(0.0, 1.0);
        let top_k = if req.top_k < 1 { 1 } else { req.top_k };

        // Parse timestamps once so we can normalize recency.
        let mut ts_vals: Vec<i64> = req
            .candidates
            .iter()
            .filter_map(|c| c.timestamp.as_deref().and_then(parse_rfc3339_epoch_seconds))
            .collect();
        ts_vals.sort_unstable();
        ts_vals.dedup();
        let min_ts = ts_vals.first().copied().unwrap_or(0);
        let max_ts = ts_vals.last().copied().unwrap_or(0);
        let ts_span = (max_ts - min_ts) as f32;

        let has_query_embedding = req.query_embedding.is_some();
        let recency_weight = if has_query_embedding { 0.02f32 } else { 0.05f32 };
        let mut per_key: HashMap<String, (Candidate, f32, Option<i64>)> = HashMap::new();

        for c in req.candidates.into_iter() {
            let content_tokens = token_set(&c.content, &token_re);
            let tags_text = c.tags.join(" ");
            let tags_tokens = token_set(&tags_text, &token_re);

            let content_score = overlap_score(&query_terms, &content_tokens);
            let tag_score = overlap_score(&query_terms, &tags_tokens);
            let lexical = 0.8f32 * content_score + 0.2f32 * tag_score;

            let mut base_score = lexical;
            if let (Some(qe), Some(ce)) = (&req.query_embedding, &c.embedding) {
                if !ce.is_empty() && qe.len() == ce.len() {
                    let cos = cosine_sim(qe, &ce).max(0.0);
                    base_score = (embed_weight * cos) + ((1.0 - embed_weight) * lexical);
                }
            }

            // Type weighting (devsper routing intent).
            let type_mult = memory_type_weight(c.memory_type.as_deref());
            base_score *= type_mult;

            // Recency normalization (tie-break when scores are close).
            let ts = c
                .timestamp
                .as_deref()
                .and_then(parse_rfc3339_epoch_seconds);
            let recency_norm = if let Some(tsv) = ts {
                if ts_span > 0.0 {
                    ((tsv - min_ts) as f32) / ts_span
                } else {
                    0.0
                }
            } else {
                0.0
            };

            let final_score = base_score + (recency_weight * recency_norm);

            if req.min_similarity > 0.0 && final_score < req.min_similarity {
                continue;
            }

            // Deterministic dedup key (normalized content tokens).
            let dedup_key = signature_tokens(&c.content, &token_re, 80);
            let replace = match per_key.get(&dedup_key) {
                None => true,
                Some((best_cand, best_score, best_ts)) => {
                    let best_score_cmp =
                        best_score.partial_cmp(&final_score).unwrap_or(std::cmp::Ordering::Equal);
                    if best_score_cmp == std::cmp::Ordering::Greater {
                        false
                    } else if best_score_cmp == std::cmp::Ordering::Less {
                        true
                    } else {
                        let best_ts_val = best_ts.unwrap_or(i64::MIN);
                        let this_ts_val = ts.unwrap_or(i64::MIN);
                        if this_ts_val != best_ts_val {
                            this_ts_val > best_ts_val
                        } else {
                            c.id < best_cand.id
                        }
                    }
                }
            };

            if replace {
                per_key.insert(dedup_key, (c, final_score, ts));
            }
        }

        let mut uniques: Vec<(Candidate, f32, Option<i64>)> = per_key
            .into_iter()
            .map(|(_, v)| v)
            .collect();

        // Deterministic ordering:
        // final_score desc, timestamp desc, id asc.
        uniques.sort_by(|a, b| {
            let ord_score = b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal);
            if ord_score != std::cmp::Ordering::Equal {
                return ord_score;
            }
            let ta = a.2.unwrap_or(i64::MIN);
            let tb = b.2.unwrap_or(i64::MIN);
            if ta != tb {
                return tb.cmp(&ta);
            }
            a.0.id.cmp(&b.0.id)
        });

        let mut ranked: Vec<Ranked> = Vec::new();
        for (c, score, _) in uniques.into_iter().take(top_k) {
            ranked.push(Ranked { id: c.id, score });
        }

        let resp = RankResponse { ranked };
        let out = serde_json::to_string(&resp).unwrap_or_else(|_| "{\"ranked\":[]}".to_string());
        print!("{out}");
    } else if cmd == "format_context" {
        let req: FormatContextRequest = match serde_json::from_str(&input) {
            Ok(v) => v,
            Err(e) => {
                eprintln!("Invalid JSON input: {e}");
                std::process::exit(2);
            }
        };

        let mut lines: Vec<String> = Vec::new();
        if !req.user_injections.is_empty() {
            lines.push("USER INJECTIONS (high priority):".to_string());
            for inj in req.user_injections.into_iter() {
                let truncated = {
                    let max = 1000usize;
                    let content = inj.content;
                    if content.chars().count() > max {
                        format!("{}...", content.chars().take(max).collect::<String>())
                    } else {
                        content
                    }
                };
                lines.push(format!("- {}", truncated));
            }
        }

        let relevant: Vec<&Candidate> = req
            .ranked_candidates
            .iter()
            .filter(|c| {
                // Skip duplicates: if candidate is itself a user injection, don't render it under relevant memories.
                let tags = c.tags.as_slice();
                !tags.iter().any(|t| t == "user_injection")
            })
            .collect();

        if !relevant.is_empty() {
            if !lines.is_empty() {
                lines.push("".to_string());
            }
            lines.push("RELEVANT MEMORY (previous research notes, findings, artifacts):".to_string());
            for c in relevant.into_iter() {
                let mtype = c
                    .memory_type
                    .as_deref()
                    .filter(|s| !s.is_empty())
                    .unwrap_or("general");
                let src = c
                    .source_task
                    .as_deref()
                    .filter(|s| !s.is_empty())
                    .unwrap_or("general");
                let content = &c.content;
                let max = 500usize;
                let truncated = if content.chars().count() > max {
                    format!("{}...", content.chars().take(max).collect::<String>())
                } else {
                    content.clone()
                };
                lines.push(format!(
                    "- [{}] {}: {}",
                    mtype,
                    src,
                    truncated
                ));
            }
        }

        let context = lines.join("\n");
        let resp = FormatContextResponse { context };
        let out = serde_json::to_string(&resp).unwrap_or_else(|_| "{\"context\":\"\"}".to_string());
        print!("{out}");
    } else {
        eprintln!("Unsupported command: {}", cmd);
        std::process::exit(2);
    }
}

