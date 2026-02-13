# Credit Memo Agent

**Status:** In development — follow [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for phased rollout.

## Overview

Produces a Tier-1 banking-style credit memo for a publicly traded company from local SEC filings (PDF/Excel), financial data (CSV), and presentations (PDF).

## Architecture

Same structure as other hive templates (e.g. `tech_news_reporter`): package with `agent.py`, `config.py`, `nodes/__init__.py`, `__main__.py`, and a linear graph.

### Execution flow

```
intake → extract-data → analyze → report
```

### Nodes (4 total)

1. **intake** (event_loop) — Collect company name and source folder path (from user or CLI context). Client-facing. Writes: `company_name`, `source_folder`.
2. **extract-data** (event_loop) — List and read PDFs/CSV/Excel from `source_folder`; save JSON extracts (e.g. `filing_10k_text.json`, `income_statement.json`, `balance_sheet.json`, `cash_flow.json`). Writes: `extracts_summary`.
3. **analyze** (event_loop) — Load extracts, compute metrics and narratives (business overview, segments, industry, debt profile, leverage, risks), build prior/current year tables. Writes: `company_full_name`, `prior_year`, `current_year`, section narratives, `*_table` arrays, `credit_metrics`, etc.
4. **report** (event_loop) — Assemble HTML memo from analyze outputs (12 sections), save and serve file. Writes: `report_file`.

### Edges

- `intake` → `extract-data` (on_success, priority=1)
- `extract-data` → `analyze` (on_success, priority=1)
- `analyze` → `report` (on_success, priority=1)

### Retry behavior

Each node is an **event_loop** node. The Hive framework retries a node **during** its run when required outputs are missing (implicit judge returns RETRY with feedback like “Missing output keys: …”). Retries happen immediately inside that node—the next node is not started until the current one has set all `output_keys`. There is **no infinite retry**: each node is capped at **10 iterations** (`max_iterations` in `loop_config` in `agent.py`). If a node still has not produced the required outputs after 10 turns, it fails and the run stops (or follows an ON_FAILURE edge if one were defined). Executor-level retries are disabled for event_loop nodes (`max_retries=0` on each node) so only the internal judge-driven retry applies.

## Data Source (v1)

User provides a **folder path** containing:

```
source_folder/
├── 10-K.pdf                 # Annual report (PDF)
├── 10-K.xlsx                # 10-K Excel / financial data (optional, in addition to or instead of PDF)
├── 10-Q.pdf                 # Quarterly (optional)
├── income_statement.csv     # 3-year financials
├── balance_sheet.csv
├── cash_flow.csv
├── investor_presentation.pdf
└── debt_schedule.csv        # Optional
```

## Usage

Run from the **hive repo root** so the CLI and MCP tools resolve correctly.

### Option 1: Hive CLI (recommended, same as other templates)

```bash
cd /path/to/hive

# With your own data folder
hive run examples/templates/credit_memo_agent --input '{"company_name":"Meta","source_folder":"/path/to/your/sec_filings"}'

# With bundled test data (path must be absolute)
hive run examples/templates/credit_memo_agent --input '{"company_name":"Meta","source_folder":"'$(pwd)'/examples/templates/credit_memo_agent/test_data"}'
```

### Option 2: Interactive TUI

```bash
cd /path/to/hive
# Direct launch (no menu):
PYTHONPATH=core:examples/templates hive tui examples/templates/credit_memo_agent --model xai/grok-4-fast-reasoning

# Or browse: hive tui --model xai/grok-4-fast-reasoning
# then choose "2. Sample Agents" → Credit Memo Agent
```

**When to enter input:**

1. **To start the run** — In the **Chat REPL** (bottom panel), type something and press Enter. You can:
   - Type JSON to pre-fill: `{"company_name":"Meta","source_folder":"/path/to/your/data"}`
   - Or type anything (e.g. `go`) to start; the intake node will then ask for company name and source folder.
2. **When the agent asks** — The agent will show a clear prompt: **"Please provide: 1. Company name … 2. Source folder path …"** You can reply with `Company name, /path/to/folder` or JSON `{"company_name":"Meta","source_folder":"/path"}`. The status will show **"Waiting for your input..."** and the placeholder **"Type your response..."** — enter your answer and press Enter.

Use **Tab** to move between panels (Log, Graph, Chat). Commands: `/help`, `/pause`, `/sessions`.

**Report output:** When the run finishes, the credit memo HTML is **opened in your default browser** automatically. The TUI also shows the execution result (e.g. `report_file` filename). If the browser did not open, open the file manually from `~/.hive/agents/credit_memo_agent/data/` (the filename is shown in the result).

### Option 3: Convenience script (loads API keys from ~/.bashrc)

```bash
cd /path/to/hive
./examples/templates/credit_memo_agent/run_with_env.sh --company "Meta" --source-folder "$(pwd)/examples/templates/credit_memo_agent/test_data"
```

Optional: `--verbose` for more log output. Set `CREDIT_MEMO_AGENT_MODEL` (e.g. `xai/grok-4-fast-reasoning`) to override the default model.

### Option 4: Python module (alternative)

```bash
cd /path/to/hive
PYTHONPATH=core:examples/templates uv run python -m credit_memo_agent run --company "Meta" --source-folder "$(pwd)/examples/templates/credit_memo_agent/test_data"
```

**Info / validate:** `hive info examples/templates/credit_memo_agent` and `hive validate examples/templates/credit_memo_agent` from repo root.

## Document Output

The memo includes:

1. Executive Summary  
2. Business Overview + Credit Metrics  
3. Business Segments  
4. Industry Overview  
5. Leverage Ratios (3-year trend)  
6. Income Statement (3-year)  
7. Balance Sheet (3-year)  
8. Cash Flow Statement (3-year)  
9. Debt Profile  
10. Risks and Mitigants  
11. Credit Ratings  
12. Appendix & References  

## Implementation

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the 6-phase build plan with verifiable milestones.

## Troubleshooting: extraction and missing sections

**Why are Business Overview, Segments, Industry, or Risks "Not disclosed" or blank?**
- **Two common causes:** (1) The 10-K PDF is **image-based** (scanned), so pypdf extracts no text and `filing_10k_text.json` is empty. (2) **Other PDFs** (earnings presentation, call transcripts, exhibits) were not extracted—only the 10-K and Excel were read. The analyze node needs text from at least one of: 10-K, earnings presentation, or transcripts to fill those sections.
- **Fix:** The extract step is now instructed to read **every** PDF in the source folder (not just the 10-K) and save each to a named JSON (e.g. `earnings_presentation.json`, `earnings_transcript.json`). Re-run with the same data; if the 10-K has no text, the analyze node will use the other PDF extracts for overview, segments, and risks. If your 10-K is scanned, consider adding a text-based PDF or running OCR externally and providing the result as a text file.

**Why is 10-K text or risks summary empty?**
- The 10-K PDF may be **image-based** (scanned). The PDF tool uses pypdf and extracts only embedded text; it cannot OCR images. If `filing_10k_text.json` is empty or has only a short note, the analyze node falls back to earnings transcripts/presentation when those were saved by the extract node.
- If the PDF result was **spilled** to a file (large response), the extract node must call `load_data` on that filename and then save the **"content"** field to `filing_10k_text.json`. The extract prompt instructs this explicitly.

**Why are income/balance/cash flow tables incomplete?**
- The extract node must save the **full** Excel tool result (all columns and rows) to `income_statement.json`, `balance_sheet.json`, and `cash_flow.json`. The prompt now requires reading all three statement sheets (by name or index), using `max_rows=2000`, and saving the entire result so the analyze node sees all line items and periods.
- Ensure the Excel file has clearly named sheets (e.g. "Income Statement", "Balance Sheet", "Cash Flow") or use sheet indices 0, 1, 2 consistently.
