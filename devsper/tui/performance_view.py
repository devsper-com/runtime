"""Dashboard panel: speculative tasks, cache hits, tool usage stats."""

from textual.widgets import Static


class PerformanceView(Static):
    """Shows speculative status, cache stats, and tool usage summary."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("", *args, **kwargs)

    def set_stats(
        self,
        speculative_enabled: bool = False,
        speculative_count: int = 0,
        cache_entries: int = 0,
        tool_stats: list[dict] | None = None,
    ) -> None:
        lines = [
            "Speculative: " + ("on" if speculative_enabled else "off"),
            f"Speculative tasks: {speculative_count}",
            f"Cache entries: {cache_entries}",
            "Tools:",
        ]
        if tool_stats:
            for s in tool_stats[:8]:
                lines.append(
                    f"  {s['tool_name']}: n={s['count']} "
                    f"ok%={s['success_rate']:.0f} lat={s['avg_latency_ms']}ms"
                )
        else:
            lines.append("  (no data)")
        self.update("\n".join(lines))
