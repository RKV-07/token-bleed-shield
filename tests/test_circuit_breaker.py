from token_bleed_shield.guards.circuit_breaker import DriftCircuitBreaker, AgentAction


def test_circuit_breaker_identical_repetition():
    breaker = DriftCircuitBreaker()

    action1 = AgentAction(tool_name="search", arguments={"path": "src", "pattern": "py"})
    verdict1 = breaker.record_and_evaluate(action1)
    assert verdict1.tripped is False

    # Second identical action trips breaker
    action2 = AgentAction(tool_name="search", arguments={"path": "src", "pattern": "py"})
    verdict2 = breaker.record_and_evaluate(action2)
    assert verdict2.tripped is True
    assert "identical arguments" in verdict2.reason


def test_circuit_breaker_consecutive_errors():
    breaker = DriftCircuitBreaker()

    for i in range(2):
        verdict = breaker.record_and_evaluate(
            AgentAction(tool_name="shell", arguments={"cmd": f"fail_{i}"}, return_code=1, error_message="error")
        )
        assert verdict.tripped is False

    # 3rd consecutive error trips breaker
    verdict_fail = breaker.record_and_evaluate(
        AgentAction(tool_name="shell", arguments={"cmd": "fail_final"}, return_code=1, error_message="error")
    )
    assert verdict_fail.tripped is True
    assert "consecutive command/tool execution failures" in verdict_fail.reason
