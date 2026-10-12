"""Sliding-window drift and loop circuit breaker for autonomous agent loops."""

import hashlib
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from ..config import CircuitBreakerConfig


class AgentAction(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    return_code: Optional[int] = 0
    error_message: Optional[str] = None


class BreakerVerdict(BaseModel):
    tripped: bool
    severity: str  # "OK", "WARNING", "CRITICAL"
    reason: Optional[str] = None
    suggested_action: Optional[str] = None
    consecutive_repetitions: int = 0
    consecutive_errors: int = 0


class DriftCircuitBreaker:
    """Detects repetitive tool loops and model drift before tokens bleed exponentially."""

    def __init__(self, config: CircuitBreakerConfig = CircuitBreakerConfig()):
        self.config = config
        self.history: List[AgentAction] = []

    def _hash_args(self, args: Dict[str, Any]) -> str:
        serialized = json.dumps(args, sort_keys=True, default=str)
        return hashlib.md5(serialized.encode("utf-8")).hexdigest()

    def record_and_evaluate(self, action: AgentAction) -> BreakerVerdict:
        self.history.append(action)
        window = self.history[-self.config.sliding_window_size :]

        # 1. Check identical tool + arguments repetition
        current_hash = self._hash_args(action.arguments)
        identical_count = 0
        for prior in reversed(window[:-1]):
            if prior.tool_name == action.tool_name and self._hash_args(prior.arguments) == current_hash:
                identical_count += 1
            else:
                break

        if identical_count >= self.config.max_identical_tool_args:
            return BreakerVerdict(
                tripped=True,
                severity="CRITICAL",
                reason=(
                    f"Agent invoked `{action.tool_name}` with identical arguments {identical_count + 1} times in a row."
                ),
                suggested_action="Halt execution immediately. Intervene with human input or alternative tool.",
                consecutive_repetitions=identical_count + 1,
            )

        # 2. Check consecutive error count
        error_count = 0
        for prior in reversed(window):
            if (prior.return_code is not None and prior.return_code != 0) or prior.error_message:
                error_count += 1
            else:
                break

        if error_count >= self.config.max_consecutive_errors:
            return BreakerVerdict(
                tripped=True,
                severity="CRITICAL",
                reason=f"Agent encountered {error_count} consecutive command/tool execution failures.",
                suggested_action=(
                    "Stop automated retries. Check environment configuration or pre-flight contract (.agent-env.md)."
                ),
                consecutive_errors=error_count,
            )

        # 3. Check oscillation (e.g., A -> B -> A -> B -> A)
        if len(window) >= 4:
            names = [a.tool_name for a in window]
            if len(set(names[-4:])) == 2 and names[-1] == names[-3] and names[-2] == names[-4]:
                return BreakerVerdict(
                    tripped=True,
                    severity="WARNING",
                    reason=f"Detected cyclic oscillation pattern between `{names[-1]}` and `{names[-2]}`.",
                    suggested_action="Break the cycle. Require explicit user direction before continuing.",
                )

        return BreakerVerdict(
            tripped=False,
            severity="OK",
            consecutive_repetitions=identical_count,
            consecutive_errors=error_count,
        )

    def reset(self) -> None:
        self.history.clear()
