from devsper.budget import BudgetManager


def test_budget_consume_and_breakdown():
    b = BudgetManager(limit_usd=1.0, on_exceeded="stop")
    c = b.consume(model="gpt-4o-mini", prompt_tokens=100_000, completion_tokens=0)
    assert c is not None
    assert b.spent_usd > 0
    assert "gpt-4o-mini" in b.breakdown


def test_budget_stop_event():
    b = BudgetManager(limit_usd=0.001, on_exceeded="stop")
    b.consume(model="gpt-4o", prompt_tokens=1_000_000, completion_tokens=0)
    assert b.should_stop() is True
