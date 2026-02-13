"""
Credit Memo Agent - Produces banking-style credit memos from SEC filings and financial data.

Reads from a user-provided folder containing PDFs (10-K, 10-Q, presentations)
and CSVs (income statement, balance sheet, cash flow). Outputs a structured
credit memo with 12 sections.
"""

from .agent import CreditMemoAgent, default_agent, goal, nodes, edges
from .config import RuntimeConfig, AgentMetadata, default_config, metadata

__version__ = "1.0.0"

__all__ = [
    "CreditMemoAgent",
    "default_agent",
    "goal",
    "nodes",
    "edges",
    "RuntimeConfig",
    "AgentMetadata",
    "default_config",
    "metadata",
]
