"""
Command-line interface for llm-behavior-diff.

Provides CLI commands for running behavioral regression tests,
generating reports, and comparing model versions.
"""

import asyncio
import json
from html import escape as html_escape
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
    permutation_rate_delta_test,
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
    if include_cost and cost_a is not None and cost_b is not None:
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
        table.add_row(
            "Regression Delta Permutation p-value",
            "-",
            "-",
            f"{float(reg['permutation_p_value_two_sided']):.6f}",
        )
        table.add_row(
            "Improvement Delta Permutation p-value",
            "-",
            "-",
            f"{float(imp['permutation_p_value_two_sided']):.6f}",
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
        reg_wilson_ci = _format_run_rate_ci(significance.get("regression_rate_wilson"))
        imp_wilson_ci = _format_run_rate_ci(significance.get("improvement_rate_wilson"))
        if reg_wilson_ci is not None:
            table.add_row("Regression Rate Wilson CI (95%)", reg_wilson_ci)
        if imp_wilson_ci is not None:
            table.add_row("Improvement Rate Wilson CI (95%)", imp_wilson_ci)

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
        reg_wilson_ci = _format_run_rate_ci(significance.get("regression_rate_wilson"))
        imp_wilson_ci = _format_run_rate_ci(significance.get("improvement_rate_wilson"))
        if reg_wilson_ci is not None:
            optional_lines.append(f"- **Regression Rate Wilson CI (95%)**: {reg_wilson_ci}")
        if imp_wilson_ci is not None:
            optional_lines.append(f"- **Improvement Rate Wilson CI (95%)**: {imp_wilson_ci}")

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
    """Format report as a self-contained interactive HTML explorer."""

    def _category_items(category_map: dict[Any, int]) -> list[tuple[str, int]]:
        items: list[tuple[str, int]] = []
        for category, count in category_map.items():
            category_label = str(category.value) if hasattr(category, "value") else str(category)
            items.append((category_label, int(count)))
        return sorted(items, key=lambda item: (-item[1], item[0]))

    def _render_category_bars(items: list[tuple[str, int]]) -> str:
        if not items:
            return '<p class="muted">No categories.</p>'
        max_count = max(count for _, count in items) or 1
        rows: list[str] = []
        for label, count in items:
            width = int((count / max_count) * 100)
            rows.append(
                "<div class='bar-row'>"
                f"<span class='bar-label'>{html_escape(label)}</span>"
                "<div class='bar-track'>"
                f"<div class='bar-fill' style='width:{width}%'></div>"
                "</div>"
                f"<span class='bar-count'>{count}</span>"
                "</div>"
            )
        return "".join(rows)

    processed_tests = report.metadata.get("processed_tests")
    failed_tests = report.metadata.get("failed_tests")
    pricing_source = report.metadata.get("pricing_source")
    estimated_cost = _extract_total_estimated_cost(report)
    significance = _extract_run_significance(report)

    significance_summary = "N/A"
    if significance is not None:
        significance_summary = (
            f"{significance['method']} (CL={significance['confidence_level']}, "
            f"B={significance['resamples']}, seed={significance['seed']})"
        )
    regression_ci = (
        _format_run_rate_ci(significance.get("regression_rate"))
        if significance is not None
        else None
    )
    improvement_ci = (
        _format_run_rate_ci(significance.get("improvement_rate"))
        if significance is not None
        else None
    )

    reg_items = _category_items(report.regression_by_category)
    imp_items = _category_items(report.improvement_by_category)

    diff_rows: list[dict[str, Any]] = []
    for index, result in enumerate(report.diff_results):
        behavior_category = (
            result.behavior_category.value
            if hasattr(result.behavior_category, "value")
            else str(result.behavior_category)
        )
        semantic_only = bool(
            result.is_semantically_same and result.response_a.strip() != result.response_b.strip()
        )
        unknown = bool(
            not result.is_semantically_same
            and not result.is_regression
            and not result.is_improvement
        )
        diff_rows.append(
            {
                "index": index,
                "test_id": result.test_id,
                "behavior_category": behavior_category,
                "semantic_similarity": float(result.semantic_similarity),
                "is_regression": bool(result.is_regression),
                "is_improvement": bool(result.is_improvement),
                "is_semantic_only": semantic_only,
                "is_unknown": unknown,
                "confidence": float(result.confidence),
                "explanation": result.explanation,
                "response_a": result.response_a,
                "response_b": result.response_b,
                "comparators": result.metadata.get("comparators", {}),
                "judge": result.metadata.get("judge"),
            }
        )

    category_options = "".join(
        f"<option value='{html_escape(category)}'>{html_escape(category)}</option>"
        for category in sorted(
            {row["behavior_category"] for row in diff_rows if row["behavior_category"]}
        )
    )
    diff_json = json.dumps(diff_rows, ensure_ascii=False, default=str).replace("</", "<\\/")

    css = """
<style>
:root {
  color-scheme: light;
  --bg: #f6f7fb;
  --card: #ffffff;
  --text: #151824;
  --muted: #5f667a;
  --line: #d8dced;
  --blue: #2f5cff;
  --red: #c4372f;
  --green: #1f8b4c;
  --amber: #b06a14;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.container {
  max-width: 1320px;
  margin: 0 auto;
  padding: 24px;
}
h1, h2, h3 { margin: 0 0 12px 0; }
.subtitle { color: var(--muted); margin-bottom: 16px; }
.section {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px;
}
.card {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
  background: #fafbff;
}
.card .label { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
.card .value { font-size: 18px; font-weight: 600; }
.card .value.red { color: var(--red); }
.card .value.green { color: var(--green); }
.filters {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}
.filters input, .filters select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  background: #fff;
}
.muted { color: var(--muted); }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th, td {
  border-bottom: 1px solid var(--line);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}
th button {
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text);
  font-weight: 600;
  padding: 0;
}
tr.row-selectable { cursor: pointer; }
tr.row-selectable:hover { background: #f3f6ff; }
tr.selected { background: #eaf0ff; }
.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 11px;
  border: 1px solid var(--line);
}
.badge.regression { background: #ffe8e6; color: var(--red); border-color: #f2c4bf; }
.badge.improvement { background: #e7f8ef; color: var(--green); border-color: #bde6cc; }
.badge.semantic-only { background: #edf0ff; color: #3d56c9; border-color: #c7d2ff; }
.badge.unknown { background: #fff3e5; color: var(--amber); border-color: #f1d6af; }
.details {
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 12px;
  background: #fcfdff;
}
.details-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
pre {
  margin: 6px 0 0 0;
  background: #10131a;
  color: #f4f6ff;
  padding: 10px;
  border-radius: 8px;
  overflow-x: auto;
  white-space: pre-wrap;
}
.bar-row {
  display: grid;
  grid-template-columns: minmax(130px, 1fr) 3fr 40px;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}
.bar-track {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: #edf0fb;
}
.bar-fill {
  height: 8px;
  border-radius: 999px;
  background: var(--blue);
}
.split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 920px) {
  .filters { grid-template-columns: 1fr; }
  .split { grid-template-columns: 1fr; }
  .details-grid { grid-template-columns: 1fr; }
}
</style>
"""

    script = """
<script>
const diffData = __DIFF_DATA__;
const tbody = document.getElementById("diffTableBody");
const searchInput = document.getElementById("searchInput");
const statusFilter = document.getElementById("statusFilter");
const categoryFilter = document.getElementById("categoryFilter");
const emptyState = document.getElementById("noDiffRows");
const tableWrapper = document.getElementById("tableWrapper");
const detailsPanel = document.getElementById("details-panel");
const sortButtons = Array.from(document.querySelectorAll("[data-sort-key]"));
let sortState = { key: "test_id", direction: "asc" };
let selectedIndex = null;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function rowStatus(row) {
  if (row.is_regression) return "regression";
  if (row.is_improvement) return "improvement";
  if (row.is_semantic_only) return "semantic-only";
  if (row.is_unknown) return "unknown";
  return "other";
}

function isNumericKey(key) {
  return key === "semantic_similarity" || key === "confidence";
}

function compareValues(a, b, key) {
  let left = a[key];
  let right = b[key];
  if (isNumericKey(key)) return Number(left) - Number(right);
  return String(left).localeCompare(String(right));
}

function matchesFilters(row) {
  const query = searchInput.value.trim().toLowerCase();
  const status = statusFilter.value;
  const category = categoryFilter.value;
  const text = `${row.test_id} ${row.explanation || ""}`.toLowerCase();

  if (query && !text.includes(query)) return false;
  if (status !== "all" && rowStatus(row) !== status) return false;
  if (category !== "all" && row.behavior_category !== category) return false;
  return true;
}

function getVisibleRows() {
  const rows = diffData.filter(matchesFilters);
  rows.sort((a, b) => {
    const base = compareValues(a, b, sortState.key);
    return sortState.direction === "asc" ? base : -base;
  });
  return rows;
}

function renderDetails(row) {
  if (!row) {
    detailsPanel.innerHTML = "<span class='muted'>Select a row to inspect responses and comparator metadata.</span>";
    return;
  }
  const comparatorJson = escapeHtml(JSON.stringify(row.comparators || {}, null, 2));
  const judgeJson = row.judge == null ? "N/A" : escapeHtml(JSON.stringify(row.judge, null, 2));
  detailsPanel.innerHTML = `
    <h3>Detail: ${escapeHtml(row.test_id)}</h3>
    <p><strong>Category:</strong> ${escapeHtml(row.behavior_category)} | <strong>Status:</strong> ${rowStatus(row)} | <strong>Confidence:</strong> ${Number(row.confidence).toFixed(2)}</p>
    <p><strong>Explanation:</strong> ${escapeHtml(row.explanation || "N/A")}</p>
    <div class="details-grid">
      <div>
        <strong>Response A</strong>
        <pre>${escapeHtml(row.response_a || "")}</pre>
      </div>
      <div>
        <strong>Response B</strong>
        <pre>${escapeHtml(row.response_b || "")}</pre>
      </div>
    </div>
    <div class="details-grid">
      <div>
        <strong>Comparator Breakdown</strong>
        <pre>${comparatorJson}</pre>
      </div>
      <div>
        <strong>Judge Metadata</strong>
        <pre>${judgeJson}</pre>
      </div>
    </div>
  `;
}

function renderTable() {
  const rows = getVisibleRows();
  if (rows.length === 0) {
    emptyState.style.display = "block";
    tableWrapper.style.display = "none";
    selectedIndex = null;
    renderDetails(null);
    return;
  }

  emptyState.style.display = "none";
  tableWrapper.style.display = "block";

  const visibleIds = new Set(rows.map((row) => row.index));
  if (selectedIndex != null && !visibleIds.has(selectedIndex)) {
    selectedIndex = null;
  }

  tbody.innerHTML = rows.map((row) => {
    const status = rowStatus(row);
    const selectedClass = selectedIndex === row.index ? "selected" : "";
    return `
      <tr class="row-selectable ${selectedClass}" data-index="${row.index}">
        <td>${escapeHtml(row.test_id)}</td>
        <td>${escapeHtml(row.behavior_category)}</td>
        <td>${Number(row.semantic_similarity).toFixed(3)}</td>
        <td>${row.is_regression ? "yes" : "no"}</td>
        <td>${row.is_improvement ? "yes" : "no"}</td>
        <td>${Number(row.confidence).toFixed(2)}</td>
        <td><span class="badge ${status}">${status}</span></td>
      </tr>
    `;
  }).join("");

  Array.from(tbody.querySelectorAll("tr")).forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      selectedIndex = Number(rowEl.dataset.index);
      const selected = diffData.find((row) => row.index === selectedIndex) || null;
      renderTable();
      renderDetails(selected);
    });
  });

  const selected = selectedIndex == null
    ? null
    : diffData.find((row) => row.index === selectedIndex) || null;
  renderDetails(selected);
}

searchInput.addEventListener("input", renderTable);
statusFilter.addEventListener("change", renderTable);
categoryFilter.addEventListener("change", renderTable);
sortButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.sortKey;
    if (sortState.key === key) {
      sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
    } else {
      sortState.key = key;
      sortState.direction = "asc";
    }
    renderTable();
  });
});

renderTable();
</script>
""".replace("__DIFF_DATA__", diff_json)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Behavioral Diff Explorer</title>
  {css}
</head>
<body>
  <div class="container">
    <h1>Behavioral Diff Explorer</h1>
    <p class="subtitle">
      {html_escape(report.model_a)} vs {html_escape(report.model_b)} | Suite: {html_escape(report.suite_name)}
    </p>

    <section class="section">
      <h2>KPIs</h2>
      <div class="cards" id="kpi-cards" data-test="kpi-cards">
        <div class="card"><div class="label">Total Tests</div><div class="value">{report.total_tests}</div></div>
        <div class="card"><div class="label">Total Differences</div><div class="value">{report.total_diffs}</div></div>
        <div class="card"><div class="label">Regressions</div><div class="value red">{report.regressions}</div></div>
        <div class="card"><div class="label">Improvements</div><div class="value green">{report.improvements}</div></div>
        <div class="card"><div class="label">Regression Rate</div><div class="value">{report.regression_rate():.2f}%</div></div>
        <div class="card"><div class="label">Improvement Rate</div><div class="value">{report.improvement_rate():.2f}%</div></div>
        <div class="card"><div class="label">Duration</div><div class="value">{report.duration_seconds:.2f}s</div></div>
      </div>
    </section>

    <section class="section">
      <h2>Optional Metadata</h2>
      <div class="cards">
        <div class="card"><div class="label">Processed Tests</div><div class="value">{processed_tests if isinstance(processed_tests, int) else "N/A"}</div></div>
        <div class="card"><div class="label">Failed Tests</div><div class="value">{failed_tests if isinstance(failed_tests, int) else "N/A"}</div></div>
        <div class="card"><div class="label">Estimated Cost (USD)</div><div class="value">{f"{estimated_cost:.8f}" if estimated_cost is not None else "N/A"}</div></div>
        <div class="card"><div class="label">Pricing Source</div><div class="value">{html_escape(pricing_source) if isinstance(pricing_source, str) else "N/A"}</div></div>
        <div class="card"><div class="label">Significance</div><div class="value">{html_escape(significance_summary)}</div></div>
        <div class="card"><div class="label">Regression CI (95%)</div><div class="value">{html_escape(regression_ci) if regression_ci else "N/A"}</div></div>
        <div class="card"><div class="label">Improvement CI (95%)</div><div class="value">{html_escape(improvement_ci) if improvement_ci else "N/A"}</div></div>
      </div>
    </section>

    <section class="section">
      <h2>Category Breakdown</h2>
      <div class="split">
        <div>
          <h3>Regression Categories</h3>
          {_render_category_bars(reg_items)}
        </div>
        <div>
          <h3>Improvement Categories</h3>
          {_render_category_bars(imp_items)}
        </div>
      </div>
    </section>

    <section class="section">
      <h2>Diff Explorer</h2>
      <div class="filters" id="explorer-filters" data-test="explorer-filters">
        <input id="searchInput" type="text" placeholder="Search test_id or explanation" />
        <select id="statusFilter">
          <option value="all">all statuses</option>
          <option value="regression">regression</option>
          <option value="improvement">improvement</option>
          <option value="semantic-only">semantic-only</option>
          <option value="unknown">unknown</option>
        </select>
        <select id="categoryFilter">
          <option value="all">all categories</option>
          {category_options}
        </select>
      </div>

      <div id="noDiffRows" class="muted" style="display:none;" data-test="no-diff-rows">
        No diff rows for this report.
      </div>

      <div id="tableWrapper">
        <table id="diff-explorer-table" data-test="diff-explorer-table">
          <thead>
            <tr>
              <th><button data-sort-key="test_id">test_id</button></th>
              <th><button data-sort-key="behavior_category">behavior_category</button></th>
              <th><button data-sort-key="semantic_similarity">semantic_similarity</button></th>
              <th><button data-sort-key="is_regression">is_regression</button></th>
              <th><button data-sort-key="is_improvement">is_improvement</button></th>
              <th><button data-sort-key="confidence">confidence</button></th>
              <th>status</th>
            </tr>
          </thead>
          <tbody id="diffTableBody"></tbody>
        </table>
      </div>

      <div id="details-panel" class="details" data-test="details-panel">
        <span class="muted">Select a row to inspect responses and comparator metadata.</span>
      </div>
    </section>
  </div>
  {script}
</body>
</html>"""


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
        metrics_table += (
            f"| Regression Delta Permutation p-value | - | - | "
            f"{float(reg['permutation_p_value_two_sided']):.6f} |\n"
        )
        metrics_table += (
            f"| Improvement Delta Permutation p-value | - | - | "
            f"{float(imp['permutation_p_value_two_sided']):.6f} |\n"
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
    regression_permutation = permutation_rate_delta_test(
        regression_a,
        regression_b,
        resamples=DEFAULT_BOOTSTRAP_RESAMPLES,
        seed=DEFAULT_BOOTSTRAP_SEED,
    )
    improvement_permutation = permutation_rate_delta_test(
        improvement_a,
        improvement_b,
        resamples=DEFAULT_BOOTSTRAP_RESAMPLES,
        seed=DEFAULT_BOOTSTRAP_SEED,
    )
    if (
        regression_delta is None
        or improvement_delta is None
        or regression_permutation is None
        or improvement_permutation is None
    ):
        return None

    regression_payload = {
        **regression_delta,
        "permutation_p_value_two_sided": float(regression_permutation["p_value_two_sided"]),
        "permutation_significant": bool(regression_permutation["significant"]),
    }
    improvement_payload = {
        **improvement_delta,
        "permutation_p_value_two_sided": float(improvement_permutation["p_value_two_sided"]),
        "permutation_significant": bool(improvement_permutation["significant"]),
    }
    return {
        "regression_delta": regression_payload,
        "improvement_delta": improvement_payload,
    }


def _format_delta_ci_percent_points(payload: dict[str, float | bool]) -> str:
    ci_low = float(payload["ci_low"]) * 100.0
    ci_high = float(payload["ci_high"]) * 100.0
    return f"[{ci_low:+.2f}, {ci_high:+.2f}] pp"


if __name__ == "__main__":
    main()
