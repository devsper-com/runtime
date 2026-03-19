//! Clarification (HITL) protocol: detect MCQ in agent response, build request payload, parse response.
//! Matches Python devsper.events.ClarificationRequest / ClarificationResponse and bus topics.

use regex::Regex;
use serde_json::{json, Value};

/// Detect if agent result text looks like a clarification MCQ (numbered question + - A:/B:/C: options).
pub fn is_clarification_response(text: &str) -> bool {
    let t = text.trim();
    if t.is_empty() {
        return false;
    }
    // Numbered question: at start or after newline, e.g. "1) ..." or "\n1) ..."
    let numbered = Regex::new(r"(?:^|\n)\d+\)\s+").unwrap();
    // MCQ options: - A: ... - B: ...
    let mcq_opts = Regex::new(r"-\s+[A-D]:\s+").unwrap();
    numbered.is_match(t) && mcq_opts.is_match(t)
}

/// One MCQ field (question + options). Serializes to Python ClarificationField shape.
#[derive(Debug)]
pub struct McqField {
    pub question: String,
    pub options: Vec<String>,
}

/// Parse the first MCQ block from agent text: "1) Question\n- A: opt1\n- B: opt2" -> McqField.
pub fn parse_mcq_from_response(text: &str) -> Option<McqField> {
    let opt_re = Regex::new(r"-\s+[A-D]:\s+(.+)").unwrap();
    let mut question = String::new();
    let mut options: Vec<String> = Vec::new();
    for line in text.lines() {
        let line = line.trim();
        if let Some(cap) = opt_re.captures(line) {
            if let Some(m) = cap.get(1) {
                options.push(m.as_str().trim().to_string());
            }
        } else if line.starts_with(|c: char| c.is_ascii_digit()) {
            if let Some(right) = line.find(')') {
                let q = line[right + 1..].trim();
                if !q.is_empty() && question.is_empty() {
                    question = q.to_string();
                }
            }
        }
    }
    if question.is_empty() || options.is_empty() {
        return None;
    }
    Some(McqField { question, options })
}

/// Build ClarificationRequest-shaped payload for bus (matches Python ClarificationRequest.to_dict).
pub fn build_request_payload(
    request_id: &str,
    task_id: &str,
    agent_role: &str,
    text: &str,
    timeout_seconds: u64,
) -> Option<Value> {
    let field = parse_mcq_from_response(text)?;
    let request = json!({
        "request_id": request_id,
        "task_id": task_id,
        "agent_role": agent_role,
        "fields": [{
            "type": "mcq",
            "question": field.question,
            "options": field.options,
            "default": serde_json::Value::Null,
            "required": true
        }],
        "context": text.lines().next().unwrap_or("").trim().chars().take(200).collect::<String>(),
        "priority": 1,
        "timeout_seconds": timeout_seconds
    });
    Some(request)
}

/// Parsed clarification response from controller (matches Python ClarificationResponse).
#[derive(Debug, Clone)]
pub struct ClarificationResponsePayload {
    pub request_id: String,
    pub answers: std::collections::HashMap<String, String>,
    pub skipped: bool,
}

pub fn parse_clarification_response(payload: &serde_json::Value) -> Option<ClarificationResponsePayload> {
    let obj = payload.as_object()?;
    let request_id = obj.get("request_id")?.as_str()?.to_string();
    let skipped = obj.get("skipped").and_then(|v| v.as_bool()).unwrap_or(false);
    let answers = obj
        .get("answers")
        .and_then(|v| v.as_object())
        .map(|m| {
            m.iter()
                .filter_map(|(k, v)| Some((k.clone(), v.as_str()?.to_string())))
                .collect()
        })
        .unwrap_or_default();
    Some(ClarificationResponsePayload {
        request_id,
        answers,
        skipped,
    })
}

/// Format user clarification for appending to task description (matches Python agent enrichment).
pub fn format_clarification_context(answers: &std::collections::HashMap<String, String>) -> String {
    if answers.is_empty() {
        return String::new();
    }
    let lines: Vec<String> = answers
        .iter()
        .map(|(q, a)| format!("{}: {}", q.trim(), a.trim()))
        .collect();
    format!("\n\n[User provided clarification:]\n{}", lines.join("\n"))
}
