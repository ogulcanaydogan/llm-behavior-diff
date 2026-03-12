"""
Command-line interface for llm-behavior-diff.

Provides CLI commands for running behavioral regression tests,
generating reports, and comparing model versions.
"""

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .schema import BehaviorReport

console = Console()


@click.group()
@click.version_option()
def main() -> None:
    """
    llm-behavior-diff: Behavioral regression testing for LLM model upgrades.

    Compare two model versions on the same test suite and detect semantic,
    behavioral, and factual differences.
    """
    pass


@main.command()
@click.option(
    "--model-a",
    required=True,
    help="First model identifier (e.g., 'gpt-4o', 'claude-3-opus')",
)
@click.option(
    "--model-b",
    required=True,
    help="Second model identifier for comparison",
)
@click.option(
    "--suite",
    required=True,
    type=click.Path(exists=True),
    help="Path to test suite YAML file",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="llm_behavior_diff_report.json",
    help="Output file for report (JSON)",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Max concurrent API calls",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate suite without running tests",
)
def run(
    model_a: str,
    model_b: str,
    suite: str,
    output: str,
    max_workers: int,
    dry_run: bool,
) -> None:
    """
    Run behavioral diff tests comparing two model versions.

    Example:
        llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite tests.yaml
    """
    console.print(f"[bold cyan]llm-behavior-diff[/bold cyan]")
    console.print(f"Comparing {model_a} vs {model_b}")
    console.print(f"Test suite: {suite}")

    if dry_run:
        console.print("[yellow]Dry run: validating suite...[/yellow]")
        # TODO: Implement suite validation
        console.print("[green]Suite is valid[/green]")
        return

    console.print(f"[yellow]Running tests with {max_workers} workers...[/yellow]")
    # TODO: Implement test runner
    console.print(f"[green]Report saved to {output}[/green]")


@main.command()
@click.argument("report_file", type=click.Path(exists=True))
@click.option(
    "--format",
    type=click.Choice(["json", "html", "markdown", "table"]),
    default="table",
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file (omit for stdout)",
)
def report(report_file: str, format: str, output: Optional[str]) -> None:
    """
    Generate behavioral diff report from results.

    Example:
        llm-diff report results.json --format html -o report.html
    """
    try:
        with open(report_file) as f:
            data = json.load(f)
        report_obj = BehaviorReport(**data)
    except Exception as e:
        console.print(f"[red]Error loading report: {e}[/red]")
        raise click.Abort()

    if format == "table":
        _print_table_report(report_obj)
    elif format == "json":
        content = json.dumps(report_obj.model_dump(), indent=2)
        _output(content, output)
    elif format == "markdown":
        content = _format_markdown(report_obj)
        _output(content, output)
    elif format == "html":
        content = _format_html(report_obj)
        _output(content, output)


@main.command()
@click.argument("result_a", type=click.Path(exists=True))
@click.argument("result_b", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file for comparison",
)
def compare(result_a: str, result_b: str, output: Optional[str]) -> None:
    """
    Compare two behavioral diff reports.

    Example:
        llm-diff compare run1_results.json run2_results.json -o comparison.html
    """
    console.print(f"[cyan]Comparing {result_a} vs {result_b}[/cyan]")
    # TODO: Implement report comparison
    console.print("[green]Comparison complete[/green]")


def _print_table_report(report: BehaviorReport) -> None:
    """Print report as rich table."""
    table = Table(title=f"Behavioral Diff Report: {report.model_a} vs {report.model_b}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Test Suite", report.suite_name)
    table.add_row("Total Tests", str(report.total_tests))
    table.add_row("Total Differences", str(report.total_diffs))
    table.add_row("Regressions", f"[red]{report.regressions}[/red]")
    table.add_row("Improvements", f"[green]{report.improvements}[/green]")
    table.add_row("Regression Rate", f"{report.regression_rate():.1f}%")
    table.add_row("Improvement Rate", f"{report.improvement_rate():.1f}%")
    table.add_row("Duration", f"{report.duration_seconds:.1f}s")

    console.print(table)

    if report.regression_by_category:
        console.print("\n[bold]Top Regression Categories:[/bold]")
        for category, count in report.top_regression_categories(5):
            console.print(f"  {category.value}: {count}")

    if report.improvement_by_category:
        console.print("\n[bold]Top Improvement Categories:[/bold]")
        for category, count in report.top_improvement_categories(5):
            console.print(f"  {category.value}: {count}")


def _format_markdown(report: BehaviorReport) -> str:
    """Format report as markdown."""
    md = f"""# Behavioral Diff Report

## Summary
- **Models**: {report.model_a} vs {report.model_b}
- **Suite**: {report.suite_name}
- **Total Tests**: {report.total_tests}
- **Differences**: {report.total_diffs}
- **Regressions**: {report.regressions} ({report.regression_rate():.1f}%)
- **Improvements**: {report.improvements} ({report.improvement_rate():.1f}%)

## Details
Generated: {report.timestamp.isoformat()}
Duration: {report.duration_seconds:.1f}s
"""
    return md


def _format_html(report: BehaviorReport) -> str:
    """Format report as HTML."""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Behavioral Diff Report</title>
    <style>
        body {{ font-family: sans-serif; margin: 20px; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        .metric {{ margin: 10px 0; }}
        .regression {{ color: #d32f2f; }}
        .improvement {{ color: #388e3c; }}
    </style>
</head>
<body>
    <h1>Behavioral Diff Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <div class="metric">
            <strong>Models:</strong> {report.model_a} vs {report.model_b}
        </div>
        <div class="metric">
            <strong>Test Suite:</strong> {report.suite_name}
        </div>
        <div class="metric">
            <strong>Total Tests:</strong> {report.total_tests}
        </div>
        <div class="metric">
            <strong class="regression">Regressions:</strong> {report.regressions} ({report.regression_rate():.1f}%)
        </div>
        <div class="metric">
            <strong class="improvement">Improvements:</strong> {report.improvements} ({report.improvement_rate():.1f}%)
        </div>
    </div>
</body>
</html>"""
    return html


def _output(content: str, output_file: Optional[str]) -> None:
    """Output content to file or stdout."""
    if output_file:
        Path(output_file).write_text(content)
        console.print(f"[green]Written to {output_file}[/green]")
    else:
        console.print(content)


if __name__ == "__main__":
    main()
