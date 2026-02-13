"""
Runtime configuration for the Credit Memo Agent.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


def _load_preferred_model() -> str:
    """Load preferred model from ~/.hive/configuration.json."""
    config_path = Path.home() / ".hive" / "configuration.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
            llm = config.get("llm", {})
            if llm.get("provider") and llm.get("model"):
                return f"{llm['provider']}/{llm['model']}"
        except Exception:
            pass
    return "anthropic/claude-sonnet-4-20250514"


@dataclass
class RuntimeConfig:
    """Runtime settings for the agent (model, temperature, tokens, API)."""

    model: str = field(default_factory=_load_preferred_model)
    temperature: float = 0.35  # Slightly higher for more interpretive depth
    max_tokens: int = 40000
    api_key: str | None = None
    api_base: str | None = None


default_config = RuntimeConfig()


@dataclass
class AgentMetadata:
    """Public metadata for the agent (name, version, description)."""

    name: str = "Credit Memo Agent"
    version: str = "1.0.0"
    description: str = (
        "Produces a banking-style credit memo for publicly traded companies "
        "from local SEC filings (PDF), financial data (CSV), and presentations."
    )


metadata = AgentMetadata()
