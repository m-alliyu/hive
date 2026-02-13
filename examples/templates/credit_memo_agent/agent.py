"""
Agent graph construction for the Credit Memo Agent.

Defines the goal, success criteria, constraints, nodes, edges, and the
CreditMemoAgent class that builds and runs the 4-node pipeline.
"""

import os

from framework.graph import EdgeSpec, EdgeCondition, Goal, SuccessCriterion, Constraint
from framework.graph.edge import GraphSpec
from framework.graph.executor import ExecutionResult, GraphExecutor
from framework.runtime.event_bus import EventBus
from framework.runtime.core import Runtime
from framework.llm import LiteLLMProvider
from framework.runner.tool_registry import ToolRegistry

from .config import default_config, get_llm_api_key_from_env, metadata
from .nodes import (
    intake_node,
    extract_data_node,
    analyze_node,
    report_node,
)

# ---------------------------------------------------------------------------
# Goal and evaluation criteria
# ---------------------------------------------------------------------------
goal = Goal(
    id="credit-memo",
    name="Credit Memo Generator",
    description=(
        "Produce a Tier-1 banking-style credit memo for a publicly traded company "
        "from local SEC filings (PDF), financial data (CSV), and presentations. "
        "All data must be traceable to source documents; no fabrication."
    ),
    success_criteria=[
        SuccessCriterion(
            id="sc-all-sections",
            description="Memo contains all 12 required sections (Executive Summary through Appendix)",
            metric="sections_present",
            target="12",
            weight=0.2,
        ),
        SuccessCriterion(
            id="sc-source-attribution",
            description="Every financial figure and material claim cites its source document",
            metric="source_attribution",
            target="100%",
            weight=0.25,
        ),
        SuccessCriterion(
            id="sc-credit-metrics",
            description="Key credit metrics computed: EBITDA, leverage ratios, coverage ratios where data allows",
            metric="metrics_computed",
            target=">=5",
            weight=0.2,
        ),
        SuccessCriterion(
            id="sc-3year-financials",
            description="Income statement, balance sheet, and cash flow include 3-year data where available",
            metric="financials_years",
            target=">=3",
            weight=0.2,
        ),
        SuccessCriterion(
            id="sc-deliverable",
            description="Memo delivered as viewable HTML file to the user",
            metric="report_delivered",
            target="true",
            weight=0.15,
        ),
    ],
    constraints=[
        Constraint(
            id="c-no-fabrication",
            description="Never fabricate financial figures, URLs, or source documents",
            constraint_type="hard",
            category="accuracy",
        ),
        Constraint(
            id="c-cite-sources",
            description="Every number and material claim must cite the source file (e.g., 10-K p. X)",
            constraint_type="hard",
            category="quality",
        ),
        Constraint(
            id="c-navigate-gaps",
            description="Where data is missing, mark as N/A or 'Not disclosed' — do not infer or guess",
            constraint_type="hard",
            category="accuracy",
        ),
        Constraint(
            id="c-professional-tone",
            description="Memo must use professional, objective banking language — no speculation or opinion",
            constraint_type="quality",
            category="tone",
        ),
        Constraint(
            id="c-disclaim-assumptions",
            description="Clearly disclose any assumptions (e.g., calculation methodology) in the memo",
            constraint_type="quality",
            category="transparency",
        ),
    ],
)

# ---------------------------------------------------------------------------
# Graph structure: nodes and edges
# ---------------------------------------------------------------------------
nodes = [
    intake_node,
    extract_data_node,
    analyze_node,
    report_node,
]

edges = [
    EdgeSpec(
        id="intake-to-extract",
        source="intake",
        target="extract-data",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
    ),
    EdgeSpec(
        id="extract-to-analyze",
        source="extract-data",
        target="analyze",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
    ),
    EdgeSpec(
        id="analyze-to-report",
        source="analyze",
        target="report",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
    ),
]

entry_node = "intake"
entry_points = {"start": "intake"}
pause_nodes = []
terminal_nodes = ["report"]


# ---------------------------------------------------------------------------
# Agent class: builds graph and runs execution
# ---------------------------------------------------------------------------
class CreditMemoAgent:
    """
    Credit Memo Agent — 4-node pipeline.

    Flow: intake -> extract-data -> analyze -> report
    """

    def __init__(self, config=None):
        self.config = config or default_config
        self.goal = goal
        self.nodes = nodes
        self.edges = edges
        self.entry_node = entry_node
        self.entry_points = entry_points
        self.pause_nodes = pause_nodes
        self.terminal_nodes = terminal_nodes
        self._executor: GraphExecutor | None = None
        self._graph: GraphSpec | None = None
        self._event_bus: EventBus | None = None
        self._tool_registry: ToolRegistry | None = None

    def _build_graph(self) -> GraphSpec:
        """Build the GraphSpec."""
        return GraphSpec(
            id="credit-memo-agent-graph",
            goal_id=self.goal.id,
            version="1.0.0",
            entry_node=self.entry_node,
            entry_points=self.entry_points,
            terminal_nodes=self.terminal_nodes,
            pause_nodes=self.pause_nodes,
            nodes=self.nodes,
            edges=self.edges,
            default_model=self.config.model,
            max_tokens=self.config.max_tokens,
            # Per-node retry cap: each event_loop node runs up to max_iterations turns.
            # The framework retries a node internally when required output_keys are missing
            # (implicit judge returns RETRY). This limit avoids infinite retries.
            loop_config={
                "max_iterations": 10,
                "max_tool_calls_per_turn": 15,
                "max_history_tokens": 32000,
            },
        )

    def _setup(self) -> GraphExecutor:
        """Set up the executor with all components."""
        from pathlib import Path

        storage_path = Path.home() / ".hive" / "agents" / "credit_memo_agent"
        storage_path.mkdir(parents=True, exist_ok=True)

        self._event_bus = EventBus()
        self._tool_registry = ToolRegistry()

        mcp_config_path = Path(__file__).parent / "mcp_servers.json"
        if mcp_config_path.exists():
            self._tool_registry.load_mcp_config(mcp_config_path)

        # Resolve API key from config or env (e.g. GEMINI_API_KEY, XAI_API_KEY)
        api_key = self.config.api_key or get_llm_api_key_from_env(self.config.model)
        # Prefer Gemini API over Vertex when GEMINI_API_KEY is set
        if self.config.model.lower().startswith("gemini/"):
            if api_key:
                for var in (
                    "GOOGLE_API_KEY",
                    "GOOGLE_APPLICATION_CREDENTIALS",
                    "VERTEXAI_PROJECT",
                    "VERTEXAI_LOCATION",
                    "VERTEXAI_CREDENTIALS",
                ):
                    os.environ.pop(var, None)
            elif not os.environ.get("GEMINI_API_KEY"):
                raise RuntimeError(
                    "Gemini model configured but GEMINI_API_KEY is not set. "
                    "Add 'export GEMINI_API_KEY=...' to ~/.bashrc and run via run_with_env.sh, "
                    "or see API_KEY_SETUP.md."
                )
        if self.config.model.lower().startswith("xai/") and not api_key:
            if not os.environ.get("XAI_API_KEY"):
                raise RuntimeError(
                    "xAI/Grok model (grok-4-fast-reasoning) requires XAI_API_KEY. "
                    "Add 'export XAI_API_KEY=...' to ~/.bashrc and run via run_with_env.sh. "
                    "(Groq is a different provider; use GROQ_API_KEY for groq/ models.)"
                )
        llm = LiteLLMProvider(
            model=self.config.model,
            api_key=api_key,
            api_base=self.config.api_base,
        )

        tool_executor = self._tool_registry.get_executor()
        tools = list(self._tool_registry.get_tools().values())

        self._graph = self._build_graph()
        runtime = Runtime(storage_path)

        self._executor = GraphExecutor(
            runtime=runtime,
            llm=llm,
            tools=tools,
            tool_executor=tool_executor,
            event_bus=self._event_bus,
            storage_path=storage_path,
            loop_config=self._graph.loop_config,
        )

        return self._executor

    async def start(self) -> None:
        """Set up the agent (initialize executor and tools)."""
        if self._executor is None:
            self._setup()

    async def stop(self) -> None:
        """Clean up resources."""
        self._executor = None
        self._event_bus = None

    async def trigger_and_wait(
        self,
        entry_point: str,
        input_data: dict,
        timeout: float | None = None,
        session_state: dict | None = None,
    ) -> ExecutionResult | None:
        """Execute the graph from the given entry point with the provided input data."""
        if self._executor is None:
            raise RuntimeError("Agent not started. Call start() first.")
        if self._graph is None:
            raise RuntimeError("Graph not built. Call start() first.")

        return await self._executor.execute(
            graph=self._graph,
            goal=self.goal,
            input_data=input_data,
            session_state=session_state,
        )

    async def run(
        self, context: dict, session_state=None
    ) -> ExecutionResult:
        """Run the agent (convenience method for single execution)."""
        await self.start()
        try:
            result = await self.trigger_and_wait(
                "start", context, session_state=session_state
            )
            return result or ExecutionResult(success=False, error="Execution timeout")
        finally:
            await self.stop()

    def info(self) -> dict:
        """Return agent metadata and graph structure (nodes, edges, entry/terminal)."""
        return {
            "name": metadata.name,
            "version": metadata.version,
            "description": metadata.description,
            "goal": {
                "name": self.goal.name,
                "description": self.goal.description,
            },
            "nodes": [n.id for n in self.nodes],
            "edges": [e.id for e in self.edges],
            "entry_node": self.entry_node,
            "entry_points": self.entry_points,
            "pause_nodes": self.pause_nodes,
            "terminal_nodes": self.terminal_nodes,
            "client_facing_nodes": [n.id for n in self.nodes if n.client_facing],
        }

    def validate(self) -> dict:
        """Validate graph structure (nodes, edges, entry/terminal nodes). Returns dict with valid, errors, warnings."""
        errors = []
        warnings = []
        node_ids = {node.id for node in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge {edge.id}: source '{edge.source}' not found")
            if edge.target not in node_ids:
                errors.append(f"Edge {edge.id}: target '{edge.target}' not found")

        if self.entry_node not in node_ids:
            errors.append(f"Entry node '{self.entry_node}' not found")

        for terminal in self.terminal_nodes:
            if terminal not in node_ids:
                errors.append(f"Terminal node '{terminal}' not found")

        for ep_id, node_id in self.entry_points.items():
            if node_id not in node_ids:
                errors.append(
                    f"Entry point '{ep_id}' references unknown node '{node_id}'"
                )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }


# Create default instance
default_agent = CreditMemoAgent()
