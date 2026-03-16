"""
Entry point for Rust worker subprocess executor.
Reads AgentRequest JSON from stdin, runs agent, writes AgentResponse JSON to stdout.
Exit 0 on success, 1 on error (error details in AgentResponse.error on stdout).
"""

import json
import sys

from devsper.credentials import inject_into_env
from devsper.agents.agent import Agent, AgentRequest, AgentResponse


def run_agent_sync(request_json: str) -> str:
    """Run agent from JSON request string; return JSON response string. Used by PyO3 executor."""
    data = json.loads(request_json)
    request = AgentRequest.from_dict(data)
    agent = Agent()
    response = agent.run(request)  # sync, not async
    return json.dumps(response.to_dict())


def main() -> None:
    # So the subprocess can use GitHub/OpenAI etc.: inject keychain credentials into env
    # (same as config resolver does for the Python worker).
    inject_into_env()
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            out = AgentResponse(
                task_id="",
                result="",
                tools_called=[],
                broadcasts=[],
                tokens_used=None,
                duration_seconds=0.0,
                error="Empty stdin",
                success=False,
            )
            print(json.dumps(out.to_dict()), flush=True)
            sys.exit(1)
        request = AgentRequest.from_dict(json.loads(raw))
    except Exception as e:
        out = AgentResponse(
            task_id="",
            result="",
            tools_called=[],
            broadcasts=[],
            tokens_used=None,
            duration_seconds=0.0,
            error=str(e),
            success=False,
        )
        print(json.dumps(out.to_dict()), flush=True)
        sys.exit(1)

    try:
        agent = Agent()
        response = agent.run(request)  # sync, not async
        print(json.dumps(response.to_dict()), flush=True)
        sys.exit(0 if response.success else 1)
    except Exception as e:
        out = AgentResponse(
            task_id=request.task.id,
            result="",
            tools_called=[],
            broadcasts=[],
            tokens_used=None,
            duration_seconds=0.0,
            error=str(e),
            success=False,
        )
        print(json.dumps(out.to_dict()), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
