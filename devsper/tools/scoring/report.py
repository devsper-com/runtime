"""
Formatting for devsper tools CLI output and analytics summary.
"""

from devsper.tools.scoring.scorer import score_label
from devsper.tools.scoring.store import ToolScore


def generate_tools_report(scores: list[ToolScore]) -> str:
    """
    Summary header: total tools, % excellent/good/degraded/poor;
    highlight top 3 and bottom 3 tools.
    """
    if not scores:
        return "No tool scores recorded."
    total = len(scores)
    excellent = sum(1 for s in scores if s.composite_score >= 0.85)
    good = sum(1 for s in scores if 0.65 <= s.composite_score < 0.85)
    degraded = sum(1 for s in scores if 0.40 <= s.composite_score < 0.65)
    poor = sum(1 for s in scores if s.composite_score < 0.40)
    p_ex = (excellent / total * 100) if total else 0
    p_good = (good / total * 100) if total else 0
    p_deg = (degraded / total * 100) if total else 0
    p_poor = (poor / total * 100) if total else 0
    lines = [
        f"Tool reliability: {total} tools tracked",
        f"  excellent: {p_ex:.0f}%  good: {p_good:.0f}%  degraded: {p_deg:.0f}%  poor: {p_poor:.0f}%",
        "",
    ]
    sorted_scores = sorted(scores, key=lambda s: -s.composite_score)
    top3 = sorted_scores[:3]
    bottom3 = sorted_scores[-3:] if len(sorted_scores) >= 3 else sorted_scores
    if top3:
        lines.append("Top 3:")
        for s in top3:
            label = score_label(s.composite_score)
            lines.append(f"  {s.tool_name}: {s.composite_score:.2f} ({label})")
        lines.append("")
    if bottom3 and (len(bottom3) < len(top3) or bottom3[0].tool_name != top3[0].tool_name):
        lines.append("Bottom 3:")
        for s in reversed(bottom3):
            label = score_label(s.composite_score)
            lines.append(f"  {s.tool_name}: {s.composite_score:.2f} ({label})")
    return "\n".join(lines)
