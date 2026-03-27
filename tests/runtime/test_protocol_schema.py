from devsper.protocol.schema import AgentExecuteRequest, AgentExecuteResponse


def test_protocol_request_defaults():
    req = AgentExecuteRequest(task_id="t1", run_id="r1", task="hello")
    assert req.config.model
    assert req.context.tools_available == []


def test_protocol_response_defaults():
    resp = AgentExecuteResponse(task_id="t1", output="ok")
    assert resp.tokens.prompt == 0
    assert resp.error is None
