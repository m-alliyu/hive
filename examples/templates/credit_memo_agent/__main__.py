"""
CLI entry point for the Credit Memo Agent.

Usage:
  python -m credit_memo_agent run --company "Meta" --source-folder /path/to/test_data
  python -m credit_memo_agent info
  python -m credit_memo_agent validate
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import click

from .agent import default_agent


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure logging level and format for agent execution."""
    if debug:
        level, fmt = logging.DEBUG, "%(asctime)s %(name)s: %(message)s"
    elif verbose:
        level, fmt = logging.INFO, "%(message)s"
    else:
        level, fmt = logging.WARNING, "%(levelname)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)
    logging.getLogger("framework").setLevel(level)


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Credit Memo Agent - Generate credit memos from SEC filings and financial data."""
    pass


@cli.command()
@click.option("--company", "-c", type=str, help="Company name for the credit memo")
@click.option("--source-folder", "-s", "source_folder", type=click.Path(exists=True), help="Path to folder with SEC filings (PDF) and financial CSVs")
@click.option("--quiet", "-q", is_flag=True, help="Only output result JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show execution details")
@click.option("--debug", is_flag=True, help="Show debug logging")
def run(company, source_folder, quiet, verbose, debug):
    """Run the agent pipeline and output JSON result."""
    if not quiet:
        setup_logging(verbose=verbose, debug=debug)

    # Build context from CLI args so intake node can use them without prompting
    context = {}
    if company:
        context["company_name"] = company
    if source_folder:
        resolved = Path(source_folder).resolve()
        if not resolved.is_dir():
            click.echo(
                f"Error: source folder is not a directory or does not exist: {source_folder}",
                err=True,
            )
            sys.exit(1)
        context["source_folder"] = str(resolved)

    result = asyncio.run(default_agent.run(context))

    output_data = {
        "success": result.success,
        "steps_executed": result.steps_executed,
        "output": result.output,
    }
    if result.error:
        output_data["error"] = result.error

    click.echo(json.dumps(output_data, indent=2, default=str))
    sys.exit(0 if result.success else 1)


@cli.command()
@click.option("--json", "output_json", is_flag=True)
def info(output_json):
    """Show agent information."""
    info_data = default_agent.info()
    if output_json:
        click.echo(json.dumps(info_data, indent=2))
    else:
        click.echo(f"Agent: {info_data['name']}")
        click.echo(f"Version: {info_data['version']}")
        click.echo(f"Description: {info_data['description']}")
        click.echo(f"\nNodes: {', '.join(info_data['nodes'])}")
        click.echo(f"Client-facing: {', '.join(info_data['client_facing_nodes'])}")
        click.echo(f"Entry: {info_data['entry_node']}")
        click.echo(f"Terminal: {', '.join(info_data['terminal_nodes'])}")


@cli.command()
def validate():
    """Validate agent structure."""
    validation = default_agent.validate()
    if validation["valid"]:
        click.echo("Agent is valid")
        if validation["warnings"]:
            for warning in validation["warnings"]:
                click.echo(f"  WARNING: {warning}")
    else:
        click.echo("Agent has errors:")
        for error in validation["errors"]:
            click.echo(f"  ERROR: {error}")
    sys.exit(0 if validation["valid"] else 1)


if __name__ == "__main__":
    cli()
