"""
Health and readiness checks for orchestration (Docker healthcheck, k8s liveness).

v1.9: bus_reachable, memory_store_readable, tool_scores_readable, knowledge_graph_loadable, checkpoint_dir_writable.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class HealthReport:
    checks: dict[str, bool]
    errors: dict[str, str]
    healthy: bool
    timestamp: str


class HealthChecker:
    """Run health checks against config subsystems."""

    async def check(self, config: object) -> HealthReport:
        checks: dict[str, bool] = {}
        errors: dict[str, str] = {}

        # bus_reachable: start and stop bus (for Redis: connect; for memory: no-op)
        try:
            from hivemind.bus import get_bus
            bus = get_bus(config)
            await bus.start()
            await bus.stop()
            checks["bus_reachable"] = True
        except Exception as e:
            checks["bus_reachable"] = False
            errors["bus_reachable"] = str(e)

        # memory_store_readable
        try:
            from hivemind.memory.memory_store import get_default_store
            store = get_default_store()
            store.list_memory(limit=1)
            checks["memory_store_readable"] = True
        except Exception as e:
            checks["memory_store_readable"] = False
            errors["memory_store_readable"] = str(e)

        # tool_scores_readable
        try:
            from hivemind.tools.scoring import get_default_score_store
            get_default_score_store().get_all_scores()
            checks["tool_scores_readable"] = True
        except Exception as e:
            checks["tool_scores_readable"] = False
            errors["tool_scores_readable"] = str(e)

        # knowledge_graph_loadable
        try:
            from hivemind.knowledge.knowledge_graph import KnowledgeGraph
            from hivemind.memory.memory_store import get_default_store
            kg = KnowledgeGraph(store=get_default_store())
            kg.load()
            checks["knowledge_graph_loadable"] = True
        except Exception as e:
            checks["knowledge_graph_loadable"] = False
            errors["knowledge_graph_loadable"] = str(e)

        # checkpoint_dir_writable
        try:
            events_dir = getattr(config, "events_dir", ".hivemind/events") or ".hivemind/events"
            import os
            os.makedirs(events_dir, exist_ok=True)
            test_file = os.path.join(events_dir, ".health_check_tmp")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            checks["checkpoint_dir_writable"] = True
        except Exception as e:
            checks["checkpoint_dir_writable"] = False
            errors["checkpoint_dir_writable"] = str(e)

        healthy = all(checks.values()) if checks else False
        return HealthReport(
            checks=checks,
            errors=errors,
            healthy=healthy,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
