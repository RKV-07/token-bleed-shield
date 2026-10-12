"""Configuration models for Token Bleed Shield."""

from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
import yaml


class ProberConfig(BaseModel):
    """Configuration for host environment probing."""
    prefer_uv: bool = True
    prefer_pnpm: bool = True
    include_git_info: bool = True
    include_os_details: bool = True
    contract_filename: str = ".agent-env.md"


class ToolLinterConfig(BaseModel):
    """Configuration for tool schema minification."""
    strip_titles: bool = True
    strip_examples: bool = False
    max_description_length: int = 140
    prune_empty_fields: bool = True


class BudgetGateConfig(BaseModel):
    """Configuration for pre-flight context budget checks."""
    max_context_tokens: int = 32000
    warn_threshold_tokens: int = 24000
    char_per_token_ratio: float = 3.8
    reject_oversized: bool = False


class CircuitBreakerConfig(BaseModel):
    """Configuration for early drift and loop termination."""
    max_consecutive_same_tools: int = 2
    max_identical_tool_args: int = 1
    max_consecutive_errors: int = 3
    sliding_window_size: int = 6


class ShieldConfig(BaseModel):
    """Root configuration for Token Bleed Shield."""
    prober: ProberConfig = Field(default_factory=ProberConfig)
    tool_linter: ToolLinterConfig = Field(default_factory=ToolLinterConfig)
    budget_gate: BudgetGateConfig = Field(default_factory=BudgetGateConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "ShieldConfig":
        if config_path and config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return cls(**data)
        
        default_path = Path(".tokenbleedshield.yaml")
        if default_path.is_file():
            with open(default_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return cls(**data)

        return cls()

    def save(self, config_path: Path = Path(".tokenbleedshield.yaml")) -> None:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)
