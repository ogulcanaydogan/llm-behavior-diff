"""
Command-line interface for llm-behavior-diff.

Provides CLI commands for running behavioral regression tests,
generating reports, and comparing model versions.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.table import Table

from .runner import BehaviorDiffRunner, load_test_suite
from .schema import BehaviorReport
from .statistics import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_CONFIDENCE_LEVEL,
    bootstrap_rate_delta_interval,
)

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
@click.option(
    "--continue-on-error",
    is_flag=True,
    help="Continue running remaining tests when one test fails",
)
@click.option(
    "--max-retries",
    type=int,
    default=3,
    show_default=True,
    help="Max retries for transient API errors per model call",
)
@click.option(
    "--rate-limit-rps",
    type=float,
    default=0.0,
    show_default=True,
    help="Per-model request rate limit (requests per second). 0 disables rate limiting",
)
@click.option(
    "--pricing-file",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional YAML/JSON file with model pricing overrides",
)
@click.option(
    "--judge-model",
    help=(
        "Optional judge model id. When set, LLM-as-judge runs only on semantic diffs and "
        "is recorded in metadata without overriding deterministic final classification"
    ),
)
def run(
    model_a: str,
    model_b: str,
    suite: str,
    output: str,
    max_workers: int,
    dry_run: bool,
    continue_on_error: bool,
    max_retries: int,
    rate_limit_rps: float,
    pricing_file: Optional[str],
    judge_model: Optional[str],
) -> None:
    """
    Run behavioral diff tests comparing two model versions.

    Example:
        llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite tests.yaml
    """
    console.print("[bold cyan]llm-behavior-diff[/bold cyan]")
    console.print(f"Comparing {model_a} vs {model_b}")
    console.print(f"Test suite: {suite}")

    try:
        suite_obj = load_test_suite(suite)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort() from exc

    if dry_run:
        console.print("[yellow]Dry run: validating suite...[/yellow]")
        console.print(
            f"[green]Suite is valid[/green] "
            f"({len(suite_obj.test_cases)} test cases, version={suite_obj.version})"
        )
        return

    console.print(f"[yellow]Running tests with {max_workers} workers...[/yellow]")
    try:
        runner = BehaviorDiffRunner(
            model_a=model_a,
            model_b=model_b,
            max_workers=max_workers,
            continue_on_error=continue_on_error,
            max_retries=max_retries,
            rate_limit_rps=rate_limit_rps,
            pricing_file=pricing_file,
            judge_model=judge_model,
        )
        report_obj = asyncio.run(runner.run_suite(suite_obj))
    except Exception as exc:
        console.print(f"[red]Run failed: {exc}[/red]")
        raise click.Abort() from exc

    Path(output).write_text(
        json.dumps(report_obj.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
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
        with open(report_file, encoding="utf-8") as f:
            data = json.load(f)
        report_obj = BehaviorReport(**data)
    except Exception as exc:
        console.print(f"[red]Error loading report: {exc}[/red]")
        raise click.Abort() from exc

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
    report_a = _load_report(result_a)
    report_b = _load_report(result_b)

    console.print(f"[cyan]Comparing {result_a} vs {result_b}[/cyan]")
    table = Table(title="Behavioral Diff Run Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Run A", style="magenta")
    table.add_column("Run B", style="magenta")
    table.add_column("Delta (B - A)", style="yellow")

    metrics: list[tuple[str, float | int, float | int]] = [
        ("Total Tests", report_a.total_tests, report_b.total_tests),
        ("Total Differences", report_a.total_diffs, report_b.total_diffs),
        ("Regressions", report_a.regressions, report_b.regressions),
        ("Improvements", report_a.improvements, report_b.improvements),
        (
            "Regression Rate (%)",
            round(report_a.regression_rate(), 2),
            round(report_b.regression_rate(), 2),
        ),
        (
            "Improvement Rate (%)",
            round(report_a.improvement_rate(), 2),
            round(report_b.improvement_rate(), 2),
        ),
        (
            "Duration (s)",
            round(report_a.duration_seconds, 2),
            round(report_b.duration_seconds, 2),
        ),
    ]
    cost_a = _extract_total_estimated_cost(report_a)
    cost_b = _extract_total_estimated_cost(report_b)
    include_cost = cost_a is not None and cost_b is not None
    if include_cost:
        metrics.append(("Estimated Cost (USD)", round(cost_a, 8), round(cost_b, 8)))

    for label, a_value, b_value in metrics:
        delta = b_value - a_value
        table.add_row(label, str(a_value), str(b_value), f"{delta:+}")

    significance_delta = _compute_compare_significance(report_a, report_b)
    if significance_delta is not None:
        reg = significance_delta["regression_delta"]
        imp = significance_delta["improvement_delta"]
        table.add_row(
            "Regression Delta CI (95%)",
            "-",
            "-",
            _format_delta_ci_percent_points(reg),
        )
        table.add_row(
            "Improvement Delta CI (95%)",
            "-",
            "-",
            _format_delta_ci_percent_points(imp),
        )
        table.add_row(
            "Regression Delta Significant?",
            "-",
            "-",
            "yes" if bool(reg["significant"]) else "no",
        )
        table.add_row(
            "Improvement Delta Significant?",
            "-",
            "-",
            "yes" if bool(imp["significant"]) else "no",
        )

    console.print(table)
    if significance_delta is None:
        console.print(
            "[yellow]Significance not available: diff_results missing or empty in one/both reports.[/yellow]"
        )

    if output:
        Path(output).write_text(
            _format_compare_markdown(
                report_a=report_a,
                report_b=report_b,
                result_a_path=result_a,
                result_b_path=result_b,
                include_cost=include_cost,
                significance_delta=significance_delta,
            ),
            encoding="utf-8",
        )
        console.print(f"[green]Comparison written to {output}[/green]")

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
    processed_tests = report.metadata.get("processed_tests")
    failed_tests = report.metadata.get("failed_tests")
    estimated_cost = _extract_total_estimated_cost(report)
    pricing_source = report.metadata.get("pricing_source")
    if isinstance(processed_tests, int):
        table.add_row("Processed Tests", str(processed_tests))
    if isinstance(failed_tests, int):
        table.add_row("Failed Tests", str(failed_tests))
    if estimated_cost is not None:
        table.add_row("Estimated Cost (USD)", f"{estimated_cost:.8f}")
    if isinstance(pricing_source, str):
        table.add_row("Pricing Source", pricing_source)
    significance = _extract_run_significance(report)
    if significance is not None:
        table.add_row(
            "Significance Method",
            (
                f"{significance['method']} "
                f"(CL={significance['confidence_level']}, "
                f"B={significance['resamples']}, seed={significance['seed']})"
            ),
        )
        table.add_row("Significance Sample Size", str(significance["sample_size"]))
        reg_ci = _format_run_rate_ci(significance.get("regression_rate"))
        imp_ci = _format_run_rate_ci(significance.get("improvement_rate"))
        if reg_ci is not None:
            table.add_row("Regression Rate CI (95%)", reg_ci)
        if imp_ci is not None:
            table.add_row("Improvement Rate CI (95%)", imp_ci)

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
    processed_tests = report.metadata.get("processed_tests")
    failed_tests = report.metadata.get("failed_tests")
    pricing_source = report.metadata.get("pricing_source")
    estimated_cost = _extract_total_estimated_cost(report)

    optional_lines = []
    if isinstance(processed_tests, int):
        optional_lines.append(f"- **Processed Tests**: {processed_tests}")
    if isinstance(failed_tests, int):
        optional_lines.append(f"- **Failed Tests**: {failed_tests}")
    if estimated_cost is not None:
        optional_lines.append(f"- **Estimated Cost (USD)**: {estimated_cost:.8f}")
    if isinstance(pricing_source, str):
        optional_lines.append(f"- **Pricing Source**: {pricing_source}")
    significance = _extract_run_significance(report)
    if significance is not None:
        optional_lines.append(
            "- **Significance Method**: "
            f"{significance['method']} (CL={significance['confidence_level']}, "
            f"B={significance['resamples']}, seed={significance['seed']})"
        )
        optional_lines.append(f"- **Significance Sample Size**: {significance['sample_size']}")
        reg_ci = _format_run_rate_ci(significance.get("regression_rate"))
        imp_ci = _format_run_rate_ci(significance.get("improvement_rate"))
        if reg_ci is not None:
            optional_lines.append(f"- **Regression Rate CI (95%)**: {reg_ci}")
        if imp_ci is not None:
            optional_lines.append(f"- **Improvement Rate CI (95%)**: {imp_ci}")

    optional_summary = ""
    if optional_lines:
        optional_summary = "\n" + "\n".join(optional_lines)

    md = f"""# Behavioral Diff Report

## Summary
- **Models**: {report.model_a} vs {report.model_b}
- **Suite**: {report.suite_name}
- **Total Tests**: {report.total_tests}
- **Differences**: {report.total_diffs}
- **Regressions**: {report.regressions} ({report.regression_rate():.1f}%)
- **Improvements**: {report.improvements} ({report.improvement_rate():.1f}%){optional_summary}

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


def _load_report(report_file: str) -> BehaviorReport:
    """Load and validate a report JSON file."""
    try:
        with open(report_file, encoding="utf-8") as file:
            return BehaviorReport(**json.load(file))
    except Exception as exc:
        console.print(f"[red]Error loading report '{report_file}': {exc}[/red]")
        raise click.Abort() from exc


def _format_compare_markdown(
    report_a: BehaviorReport,
    report_b: BehaviorReport,
    result_a_path: str,
    result_b_path: str,
    include_cost: bool,
    significance_delta: dict[str, Any] | None,
) -> str:
    """Format compare command output as markdown."""
    metrics_table = f"""| Metric | Run A | Run B | Delta (B - A) |
| --- | ---: | ---: | ---: |
| Total Tests | {report_a.total_tests} | {report_b.total_tests} | {report_b.total_tests - report_a.total_tests:+} |
| Total Differences | {report_a.total_diffs} | {report_b.total_diffs} | {report_b.total_diffs - report_a.total_diffs:+} |
| Regressions | {report_a.regressions} | {report_b.regressions} | {report_b.regressions - report_a.regressions:+} |
| Improvements | {report_a.improvements} | {report_b.improvements} | {report_b.improvements - report_a.improvements:+} |
| Regression Rate (%) | {report_a.regression_rate():.2f} | {report_b.regression_rate():.2f} | {report_b.regression_rate() - report_a.regression_rate():+.2f} |
| Improvement Rate (%) | {report_a.improvement_rate():.2f} | {report_b.improvement_rate():.2f} | {report_b.improvement_rate() - report_a.improvement_rate():+.2f} |
| Duration (s) | {report_a.duration_seconds:.2f} | {report_b.duration_seconds:.2f} | {report_b.duration_seconds - report_a.duration_seconds:+.2f} |
"""
    if include_cost:
        cost_a = _extract_total_estimated_cost(report_a) or 0.0
        cost_b = _extract_total_estimated_cost(report_b) or 0.0
        metrics_table += (
            f"| Estimated Cost (USD) | {cost_a:.8f} | {cost_b:.8f} | {cost_b - cost_a:+.8f} |\n"
        )
    if significance_delta is not None:
        reg = significance_delta["regression_delta"]
        imp = significance_delta["improvement_delta"]
        metrics_table += (
            f"| Regression Delta CI (95%) | - | - | {_format_delta_ci_percent_points(reg)} |\n"
        )
        metrics_table += (
            f"| Improvement Delta CI (95%) | - | - | {_format_delta_ci_percent_points(imp)} |\n"
        )
        metrics_table += (
            f"| Regression Delta Significant? | - | - | "
            f"{'yes' if bool(reg['significant']) else 'no'} |\n"
        )
        metrics_table += (
            f"| Improvement Delta Significant? | - | - | "
            f"{'yes' if bool(imp['significant']) else 'no'} |\n"
        )
    else:
        metrics_table += "| Significance | - | - | not available (diff_results missing/empty) |\n"

    return f"""# Behavioral Diff Comparison

- **Run A**: `{result_a_path}` ({report_a.model_a} vs {report_a.model_b}, suite: {report_a.suite_name})
- **Run B**: `{result_b_path}` ({report_b.model_a} vs {report_b.model_b}, suite: {report_b.suite_name})

{metrics_table}
"""


def _extract_total_estimated_cost(report: BehaviorReport) -> Optional[float]:
    """Extract total estimated USD cost from report metadata."""
    estimated_cost = report.metadata.get("estimated_cost_usd")
    if not isinstance(estimated_cost, dict):
        return None
    total = estimated_cost.get("total")
    if isinstance(total, (int, float)):
        return float(total)
    return None


def _extract_run_significance(report: BehaviorReport) -> dict[str, Any] | None:
    """Extract run-level significance metadata when available."""
    payload = report.metadata.get("significance")
    if not isinstance(payload, dict):
        return None
    required_keys = {
        "method",
        "confidence_level",
        "resamples",
        "seed",
        "sample_size",
        "regression_rate",
        "improvement_rate",
    }
    if not required_keys.issubset(payload):
        return None
    return payload


def _format_run_rate_ci(rate_payload: Any) -> str | None:
    if not isinstance(rate_payload, dict):
        return None
    ci_low = rate_payload.get("ci_low")
    ci_high = rate_payload.get("ci_high")
    if not isinstance(ci_low, (int, float)) or not isinstance(ci_high, (int, float)):
        return None
    return f"[{(float(ci_low) * 100):.2f}%, {(float(ci_high) * 100):.2f}%]"


def _compute_compare_significance(
    report_a: BehaviorReport, report_b: BehaviorReport
) -> dict[str, dict[str, float | bool]] | None:
    regression_a = [result.is_regression for result in report_a.diff_results]
    regression_b = [result.is_regression for result in report_b.diff_results]
    improvement_a = [result.is_improvement for result in report_a.diff_results]
    improvement_b = [result.is_improvement for result in report_b.diff_results]

    regression_delta = bootstrap_rate_delta_interval(
        regression_a,
        regression_b,
        resamples=DEFAULT_BOOTSTRAP_RESAMPLES,
        confidence_level=DEFAULT_CONFIDENCE_LEVEL,
        seed=DEFAULT_BOOTSTRAP_SEED,
    )
    improvement_delta = bootstrap_rate_delta_interval(
        improvement_a,
        improvement_b,
        resamples=DEFAULT_BOOTSTRAP_RESAMPLES,
        confidence_level=DEFAULT_CONFIDENCE_LEVEL,
        seed=DEFAULT_BOOTSTRAP_SEED,
    )
    if regression_delta is None or improvement_delta is None:
        return None
    return {
        "regression_delta": regression_delta,
        "improvement_delta": improvement_delta,
    }


def _format_delta_ci_percent_points(payload: dict[str, float | bool]) -> str:
    ci_low = float(payload["ci_low"]) * 100.0
    ci_high = float(payload["ci_high"]) * 100.0
    return f"[{ci_low:+.2f}, {ci_high:+.2f}] pp"


if __name__ == "__main__":
    main()
