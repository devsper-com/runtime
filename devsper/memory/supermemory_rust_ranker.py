"""
Local Supermemory-style hybrid ranking (no HTTP).

This is a minimal subset of Supermemory implemented for `runtime/`:
- Hybrid ranking: lexical/token overlap + optional embedding cosine similarity.
- Thresholding via `min_similarity` and truncation via `top_k`.

Not implemented here (handled elsewhere by the runtime or not at all):
- Ingestion / document processing pipeline
- Memory CRUD endpoints
- Knowledge graph relationships / versioning / forgetting semantics
- Any external Supermemory API calls

If a Rust core binary is present, we call it via subprocess (JSON in/out).
Otherwise we fall back to a pure-Python implementation so runtime behavior
does not depend on Rust build artifacts.

This module intentionally makes no HTTP calls.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


_TOKEN_RE = re.compile(r"\w+")


def _token_set(s: str) -> set[str]:
    text = s or ""
    tokens = _TOKEN_RE.findall(text.lower())
    # Keep tokens reasonably specific; matches the intent of the platform overlap scorer.
    return {t for t in tokens if len(t) >= 2}


def _overlap_score(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    # match/len(a), where a is the query term set.
    return len(a.intersection(b)) / float(len(a))


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _truncate_chars(s: str, max_chars: int) -> str:
    s = s or ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "..."


def _parse_iso_to_epoch_seconds(ts: Any) -> float | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    if not isinstance(ts, str):
        ts = str(ts)
    # Python isoformat might end with 'Z' (common), normalize to +00:00.
    ts_norm = ts.strip()
    if ts_norm.endswith("Z"):
        ts_norm = ts_norm[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(ts_norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _memory_type_weight(memory_type: Any) -> float:
    mt = (memory_type or "").lower()
    if mt == "research":
        return 1.15
    if mt == "artifact":
        return 1.10
    if mt == "semantic":
        return 1.05
    return 1.0


def _signature_tokens(s: str, *, max_tokens: int = 80) -> str:
    # Dedup key: normalized (token_set + deterministic sort) signature.
    tokens = list(_token_set(s))
    tokens.sort()
    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
    return " ".join(tokens)


def _python_format_context(*, user_injections: list[dict[str, Any]], ranked_candidates: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    if user_injections:
        lines.append("USER INJECTIONS (high priority):")
        for inj in user_injections:
            content = str(inj.get("content", "") or "")
            lines.append(f"- {_truncate_chars(content, 1000)}")

    relevant: list[dict[str, Any]] = [
        c for c in ranked_candidates if not any(t == "user_injection" for t in (c.get("tags") or []))
    ]
    if relevant:
        if lines:
            lines.append("")
        lines.append("RELEVANT MEMORY (previous research notes, findings, artifacts):")
        for c in relevant:
            mt = c.get("memory_type") or "general"
            src = c.get("source_task") or "general"
            content = str(c.get("content", "") or "")
            lines.append(f"- [{mt}] {src}: {_truncate_chars(content, 500)}")
    return "\n".join(lines) if lines else ""


def _python_rank_memories(
    *,
    query_text: str,
    query_embedding: list[float] | None,
    candidates: list[dict[str, Any]],
    top_k: int,
    min_similarity: float,
    embed_weight: float,
) -> list[dict[str, Any]]:
    query_terms = _token_set(query_text)

    # Pre-parse timestamps so we can normalize recency (stable tie-break).
    ts_vals: list[float] = []
    for c in candidates:
        ts = _parse_iso_to_epoch_seconds(c.get("timestamp"))
        if ts is not None:
            ts_vals.append(float(ts))
    if ts_vals:
        ts_vals_sorted = sorted(set(ts_vals))
        min_ts = ts_vals_sorted[0]
        max_ts = ts_vals_sorted[-1]
        ts_span = float(max_ts - min_ts) if max_ts > min_ts else 0.0
    else:
        min_ts, max_ts, ts_span = 0.0, 0.0, 0.0

    has_query_embedding = query_embedding is not None
    recency_weight = 0.02 if has_query_embedding else 0.05

    # Dedup: signature -> best candidate.
    best_by_sig: dict[str, dict[str, Any]] = {}

    for c in candidates:
        cid = str(c.get("id", ""))
        content = str(c.get("content", "") or "")
        tags = c.get("tags") or []
        tags_text = " ".join(str(t) for t in tags if t is not None)

        content_score = _overlap_score(query_terms, _token_set(content))
        tag_score = _overlap_score(query_terms, _token_set(tags_text))
        lexical = (0.8 * content_score) + (0.2 * tag_score)

        emb = c.get("embedding")
        base_score = lexical
        if (
            query_embedding is not None
            and isinstance(emb, list)
            and len(emb) == len(query_embedding)
            and emb
        ):
            cos = max(0.0, float(_cosine_sim(query_embedding, emb)))
            base_score = (embed_weight * cos) + ((1.0 - embed_weight) * lexical)

        base_score *= _memory_type_weight(c.get("memory_type"))

        ts = _parse_iso_to_epoch_seconds(c.get("timestamp"))
        recency_norm = ((ts - min_ts) / ts_span) if (ts is not None and ts_span > 0.0) else 0.0
        final_score = float(base_score) + float(recency_weight * recency_norm)

        if min_similarity > 0 and final_score < min_similarity:
            continue

        sig = _signature_tokens(content)
        best = best_by_sig.get(sig)
        if best is None:
            best_by_sig[sig] = {"id": cid, "score": final_score, "timestamp": ts or float("-inf")}
            continue

        best_score = float(best["score"])
        best_ts = float(best["timestamp"])
        if final_score > best_score:
            best_by_sig[sig] = {
                "id": cid,
                "score": final_score,
                "timestamp": ts or float("-inf"),
            }
        elif final_score == best_score:
            this_ts = ts or float("-inf")
            if this_ts > best_ts or (this_ts == best_ts and cid < best["id"]):
                best_by_sig[sig] = {
                    "id": cid,
                    "score": final_score,
                    "timestamp": this_ts,
                }

    ranked = list(best_by_sig.values())
    # Deterministic ordering: score desc, timestamp desc, id asc.
    def _ts_or_min(v: Any) -> float:
        if v is None:
            return -1e30
        try:
            fv = float(v)
            if math.isinf(fv) and fv < 0:
                return -1e30
            return fv
        except Exception:
            return -1e30

    ranked.sort(
        key=lambda x: (
            -float(x["score"]),
            -_ts_or_min(x.get("timestamp")),
            str(x["id"]),
        )
    )

    return [{"id": str(x["id"]), "score": float(x["score"])} for x in ranked[:top_k]]


def format_memory_context(
    *,
    user_injections: list[Any],
    ranked_candidates: list[Any],
) -> str:
    """
    Produce the final `memory_context` prompt string.

    This delegates to the Rust `format_context` subcommand when available,
    otherwise falls back to the same formatting behavior in Python.
    """
    bin_path = _find_rust_binary()
    # Normalize inputs to dicts (so both MemoryRecord objects and dicts work).
    def as_dict(x: Any) -> dict[str, Any]:
        if isinstance(x, dict):
            return x
        out: dict[str, Any] = {}
        for k in ["content", "tags", "timestamp", "memory_type", "source_task", "id"]:
            if hasattr(x, k):
                out[k] = getattr(x, k)
        # pydantic models sometimes expose `.model_dump()`; use if present.
        if hasattr(x, "model_dump"):
            try:
                out.update(x.model_dump())
            except Exception:
                pass
        return out

    user_inj_dicts = [as_dict(x) for x in (user_injections or [])]
    ranked_dicts = [as_dict(x) for x in (ranked_candidates or [])]

    if bin_path:
        payload = {
            "user_injections": [
                {"content": str(d.get("content", "") or ""), "tags": d.get("tags") or []}
                for d in user_inj_dicts
            ],
            "ranked_candidates": [
                {
                    "id": str(d.get("id", "") or ""),
                    "content": str(d.get("content", "") or ""),
                    "tags": d.get("tags") or [],
                    "timestamp": (d.get("timestamp").isoformat() if hasattr(d.get("timestamp"), "isoformat") else d.get("timestamp")),
                    "memory_type": (
                        d.get("memory_type").value
                        if hasattr(d.get("memory_type"), "value")
                        else d.get("memory_type")
                    ),
                    "source_task": d.get("source_task") or "",
                    "embedding": d.get("embedding"),
                }
                for d in ranked_dicts
            ],
        }
        try:
            proc = subprocess.run(
                [bin_path, "format_context"],
                input=json.dumps(payload).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5.0,
                check=False,
            )
            if proc.returncode == 0:
                out = json.loads(proc.stdout.decode("utf-8"))
                ctx = out.get("context") or ""
                return str(ctx)
        except Exception:
            pass

    return _python_format_context(
        user_injections=[
            {"content": str(d.get("content", "") or ""), "tags": d.get("tags") or []} for d in user_inj_dicts
        ],
        ranked_candidates=[
            {
                "content": str(d.get("content", "") or ""),
                "tags": d.get("tags") or [],
                "memory_type": (
                    d.get("memory_type").value
                    if hasattr(d.get("memory_type"), "value")
                    else d.get("memory_type") or "general"
                ),
                "source_task": d.get("source_task") or "general",
            }
            for d in ranked_dicts
        ],
    )


def _find_rust_binary() -> str | None:
    # Preferred override for local builds.
    override = os.environ.get("DEVSPER_SUPERMEMORY_CORE_BIN")
    if override and Path(override).is_file():
        return override

    # Best-effort lookup in repo build outputs (debug/release).
    repo_root = Path(__file__).resolve().parents[2]  # runtime/devsper/ -> runtime/
    for candidate in [
        # Workspace builds typically land here: runtime/target/{debug,release}/...
        repo_root / "target" / "release" / "devsper-supermemory-core",
        repo_root / "target" / "debug" / "devsper-supermemory-core",
        # Standalone builds land here:
        repo_root
        / "supermemory-core"
        / "target"
        / "release"
        / "devsper-supermemory-core",
        repo_root
        / "supermemory-core"
        / "target"
        / "debug"
        / "devsper-supermemory-core",
    ]:
        if candidate.is_file():
            return str(candidate)

    return None


def rank_memories(
    *,
    query_text: str,
    query_embedding: list[float] | None,
    candidates: list[dict[str, Any]],
    top_k: int = 10,
    min_similarity: float = 0.0,
    embed_weight: float = 0.7,
) -> list[dict[str, Any]]:
    """
    Rank candidates and return `[{id, score}, ...]` (already filtered + truncated).

    Scoring model (hybrid):
    - lexical score = 0.8 * content_token_overlap + 0.2 * tag_token_overlap
    - if both `query_embedding` and a candidate `embedding` are present (and same length):
      final_score = embed_weight * cosine_similarity + (1 - embed_weight) * lexical_score

    Filtering:
    - if `min_similarity > 0`, any candidate with final_score < min_similarity is dropped.

    Implementation detail:
    - prefers the local Rust binary if it exists; otherwise uses the Python fallback.
    """
    if top_k < 1:
        top_k = 1

    bin_path = _find_rust_binary()
    if not bin_path:
        return _python_rank_memories(
            query_text=query_text,
            query_embedding=query_embedding,
            candidates=candidates,
            top_k=top_k,
            min_similarity=min_similarity,
            embed_weight=embed_weight,
        )

    # Rust core path: JSON in/out via stdin/stdout.
    payload = {
        "query_text": query_text,
        "query_embedding": query_embedding,
        "top_k": top_k,
        "min_similarity": min_similarity,
        "embed_weight": embed_weight,
        "candidates": candidates,
    }
    try:
        proc = subprocess.run(
            [bin_path, "rank"],
            input=json.dumps(payload).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5.0,
            check=False,
        )
        if proc.returncode != 0:
            # Fall back if Rust fails for any reason; runtime should not crash.
            return _python_rank_memories(
                query_text=query_text,
                query_embedding=query_embedding,
                candidates=candidates,
                top_k=top_k,
                min_similarity=min_similarity,
                embed_weight=embed_weight,
            )
        out = json.loads(proc.stdout.decode("utf-8"))
        ranked = out.get("ranked") or []
        if not isinstance(ranked, list):
            raise ValueError("Invalid rust ranked payload shape")
        return ranked[:top_k]
    except Exception:
        return _python_rank_memories(
            query_text=query_text,
            query_embedding=query_embedding,
            candidates=candidates,
            top_k=top_k,
            min_similarity=min_similarity,
            embed_weight=embed_weight,
        )

