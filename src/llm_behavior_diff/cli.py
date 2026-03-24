"""
Command-line interface for llm-behavior-diff.

Provides CLI commands for running behavioral regression tests,
generating reports, and comparing model versions.
"""

import asyncio
import csv
import io
import json
import os
import xml.etree.ElementTree as ET
from html import escape as html_escape
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import click
import httpx
from rich.console import Console
from rich.table import Table

from .benchmark import build_benchmark_summary
from .policy import SUPPORTED_POLICIES, SUPPORTED_POLICY_PACKS, evaluate_report_policy
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
@click.option(
    "--factual-connector",
    type=click.Choice(["none", "wikipedia"]),
    default="none",
    show_default=True,
    help="Optional external factual connector (metadata-only, non-fatal, non-overriding)",
)
@click.option(
    "--factual-connector-timeout",
    type=float,
    default=8.0,
    show_default=True,
    help="Timeout in seconds for each external factual connector request",
)
@click.option(
    "--factual-connector-max-results",
    type=int,
    default=3,
    show_default=True,
    help="Max external factual evidence results per test",
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
    factual_connector: str,
    factual_connector_timeout: float,
    factual_connector_max_results: int,
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
            factual_connector=factual_connector,
            factual_connector_timeout=factual_connector_timeout,
            factual_connector_max_results=factual_connector_max_results,
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
    type=click.Choice(["json", "html", "markdown", "table", "csv", "ndjson", "junit"]),
    default="table",
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file (omit for stdout)",
)
@click.option(
    "--export-connector",
    type=click.Choice(
        [
            "none",
            "http",
            "s3",
            "bigquery",
            "snowflake",
            "gcs",
            "redshift",
            "azure_blob",
            "databricks",
        ]
    ),
    default="none",
    show_default=True,
    help="Optional direct export connector for rendered report output",
)
@click.option(
    "--export-endpoint",
    type=str,
    help="Export connector endpoint URL (required when --export-connector http)",
)
@click.option(
    "--export-timeout",
    type=float,
    default=10.0,
    show_default=True,
    help="Export connector timeout in seconds",
)
@click.option(
    "--export-api-key",
    type=str,
    help="Optional export API key (fallback: LLM_DIFF_EXPORT_API_KEY env var)",
)
@click.option(
    "--export-s3-bucket",
    type=str,
    help="S3 bucket name (required when --export-connector s3)",
)
@click.option(
    "--export-s3-prefix",
    type=str,
    default="",
    show_default=True,
    help="Optional S3 key prefix",
)
@click.option(
    "--export-s3-region",
    type=str,
    help="Optional S3 region override (uses AWS default chain when omitted)",
)
@click.option(
    "--export-gcs-bucket",
    type=str,
    help="GCS bucket name (required when --export-connector gcs)",
)
@click.option(
    "--export-gcs-prefix",
    type=str,
    default="",
    show_default=True,
    help="Optional GCS object prefix",
)
@click.option(
    "--export-gcs-project",
    type=str,
    help="Optional GCS project override (ADC project used when omitted)",
)
@click.option(
    "--export-az-account-url",
    type=str,
    help="Azure Blob account URL (required when --export-connector azure_blob)",
)
@click.option(
    "--export-az-container",
    type=str,
    help="Azure Blob container name (required when --export-connector azure_blob)",
)
@click.option(
    "--export-az-prefix",
    type=str,
    default="",
    show_default=True,
    help="Optional Azure Blob object prefix",
)
@click.option(
    "--export-bq-project",
    type=str,
    help="BigQuery project id (required when --export-connector bigquery)",
)
@click.option(
    "--export-bq-dataset",
    type=str,
    help="BigQuery dataset id (required when --export-connector bigquery)",
)
@click.option(
    "--export-bq-table",
    type=str,
    help="BigQuery table id (required when --export-connector bigquery)",
)
@click.option(
    "--export-bq-location",
    type=str,
    help="Optional BigQuery location override",
)
@click.option(
    "--export-sf-account",
    type=str,
    help="Snowflake account identifier (required when --export-connector snowflake)",
)
@click.option(
    "--export-sf-user",
    type=str,
    help="Snowflake user (required when --export-connector snowflake)",
)
@click.option(
    "--export-sf-password",
    type=str,
    help="Snowflake password (optional flag; fallback: LLM_DIFF_EXPORT_SF_PASSWORD)",
)
@click.option(
    "--export-sf-role",
    type=str,
    help="Optional Snowflake role",
)
@click.option(
    "--export-sf-warehouse",
    type=str,
    help="Snowflake warehouse (required when --export-connector snowflake)",
)
@click.option(
    "--export-sf-database",
    type=str,
    help="Snowflake database (required when --export-connector snowflake)",
)
@click.option(
    "--export-sf-schema",
    type=str,
    help="Snowflake schema (required when --export-connector snowflake)",
)
@click.option(
    "--export-sf-table",
    type=str,
    help="Snowflake table (required when --export-connector snowflake)",
)
@click.option(
    "--export-rs-host",
    type=str,
    help="Redshift host (required when --export-connector redshift)",
)
@click.option(
    "--export-rs-port",
    type=int,
    default=5439,
    show_default=True,
    help="Redshift port",
)
@click.option(
    "--export-rs-database",
    type=str,
    help="Redshift database (required when --export-connector redshift)",
)
@click.option(
    "--export-rs-user",
    type=str,
    help="Redshift user (required when --export-connector redshift)",
)
@click.option(
    "--export-rs-password",
    type=str,
    help="Redshift password (optional flag; fallback: LLM_DIFF_EXPORT_RS_PASSWORD)",
)
@click.option(
    "--export-rs-schema",
    type=str,
    help="Redshift schema (required when --export-connector redshift)",
)
@click.option(
    "--export-rs-table",
    type=str,
    help="Redshift table (required when --export-connector redshift)",
)
@click.option(
    "--export-rs-sslmode",
    type=str,
    default="require",
    show_default=True,
    help="Redshift sslmode",
)
@click.option(
    "--export-dbx-host",
    type=str,
    help="Databricks host (required when --export-connector databricks)",
)
@click.option(
    "--export-dbx-http-path",
    type=str,
    help="Databricks SQL HTTP path (required when --export-connector databricks)",
)
@click.option(
    "--export-dbx-token",
    type=str,
    help="Databricks PAT token (optional flag; fallback: LLM_DIFF_EXPORT_DBX_TOKEN)",
)
@click.option(
    "--export-dbx-catalog",
    type=str,
    help="Databricks catalog (required when --export-connector databricks)",
)
@click.option(
    "--export-dbx-schema",
    type=str,
    help="Databricks schema (required when --export-connector databricks)",
)
@click.option(
    "--export-dbx-table",
    type=str,
    help="Databricks table (required when --export-connector databricks)",
)
def report(
    report_file: str,
    format: str,
    output: Optional[str],
    export_connector: str,
    export_endpoint: Optional[str],
    export_timeout: float,
    export_api_key: Optional[str],
    export_s3_bucket: Optional[str],
    export_s3_prefix: str,
    export_s3_region: Optional[str],
    export_gcs_bucket: Optional[str],
    export_gcs_prefix: str,
    export_gcs_project: Optional[str],
    export_az_account_url: Optional[str],
    export_az_container: Optional[str],
    export_az_prefix: str,
    export_bq_project: Optional[str],
    export_bq_dataset: Optional[str],
    export_bq_table: Optional[str],
    export_bq_location: Optional[str],
    export_sf_account: Optional[str],
    export_sf_user: Optional[str],
    export_sf_password: Optional[str],
    export_sf_role: Optional[str],
    export_sf_warehouse: Optional[str],
    export_sf_database: Optional[str],
    export_sf_schema: Optional[str],
    export_sf_table: Optional[str],
    export_rs_host: Optional[str],
    export_rs_port: int,
    export_rs_database: Optional[str],
    export_rs_user: Optional[str],
    export_rs_password: Optional[str],
    export_rs_schema: Optional[str],
    export_rs_table: Optional[str],
    export_rs_sslmode: str,
    export_dbx_host: Optional[str],
    export_dbx_http_path: Optional[str],
    export_dbx_token: Optional[str],
    export_dbx_catalog: Optional[str],
    export_dbx_schema: Optional[str],
    export_dbx_table: Optional[str],
) -> None:
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

    rendered_content: str | None = None
    if format == "table":
        _print_table_report(report_obj)
    elif format == "json":
        rendered_content = json.dumps(report_obj.model_dump(), indent=2)
        _output(rendered_content, output)
    elif format == "markdown":
        rendered_content = _format_markdown(report_obj)
        _output(rendered_content, output)
    elif format == "html":
        rendered_content = _format_html(report_obj)
        _output(rendered_content, output)
    elif format == "csv":
        rendered_content = _format_csv(report_obj)
        _output(rendered_content, output)
    elif format == "ndjson":
        rendered_content = _format_ndjson(report_obj)
        _output(rendered_content, output)
    elif format == "junit":
        rendered_content = _format_junit(report_obj)
        _output(rendered_content, output)

    if export_connector != "none":
        if rendered_content is None:
            console.print("[red]Export connector requires non-table report format output.[/red]")
            raise click.Abort()
        try:
            _dispatch_report_export(
                report=report_obj,
                report_format=format,
                content=rendered_content,
                connector=export_connector,
                endpoint=export_endpoint,
                timeout_seconds=export_timeout,
                api_key=export_api_key,
                s3_bucket=export_s3_bucket,
                s3_prefix=export_s3_prefix,
                s3_region=export_s3_region,
                gcs_bucket=export_gcs_bucket,
                gcs_prefix=export_gcs_prefix,
                gcs_project=export_gcs_project,
                az_account_url=export_az_account_url,
                az_container=export_az_container,
                az_prefix=export_az_prefix,
                bq_project=export_bq_project,
                bq_dataset=export_bq_dataset,
                bq_table=export_bq_table,
                bq_location=export_bq_location,
                sf_account=export_sf_account,
                sf_user=export_sf_user,
                sf_password=export_sf_password,
                sf_role=export_sf_role,
                sf_warehouse=export_sf_warehouse,
                sf_database=export_sf_database,
                sf_schema=export_sf_schema,
                sf_table=export_sf_table,
                rs_host=export_rs_host,
                rs_port=export_rs_port,
                rs_database=export_rs_database,
                rs_user=export_rs_user,
                rs_password=export_rs_password,
                rs_schema=export_rs_schema,
                rs_table=export_rs_table,
                rs_sslmode=export_rs_sslmode,
                dbx_host=export_dbx_host,
                dbx_http_path=export_dbx_http_path,
                dbx_token=export_dbx_token,
                dbx_catalog=export_dbx_catalog,
                dbx_schema=export_dbx_schema,
                dbx_table=export_dbx_table,
            )
            console.print("[green]External export delivered[/green]")
        except Exception as exc:
            console.print(f"[red]Export failed: {exc}[/red]")
            raise click.Abort() from exc


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


@main.command()
@click.argument("report_file", type=click.Path(exists=True))
@click.option(
    "--policy",
    type=click.Choice(list(SUPPORTED_POLICIES)),
    default="strict",
    show_default=True,
    help="Risk-tier gate policy",
)
@click.option(
    "--policy-pack",
    type=click.Choice(list(SUPPORTED_POLICY_PACKS)),
    default="core",
    show_default=True,
    help="Built-in policy pack",
)
@click.option(
    "--policy-file",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional custom policy YAML file (takes precedence over --policy-pack)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Optional output file path",
)
def gate(
    report_file: str,
    policy: str,
    policy_pack: str,
    policy_file: Optional[str],
    output_format: str,
    output: Optional[str],
) -> None:
    """
    Evaluate one report against a deterministic gate policy.

    Example:
        llm-diff gate report.json --policy strict
        llm-diff gate report.json --policy balanced --policy-pack risk_averse
    """
    report_obj = _load_report(report_file)
    try:
        evaluation = evaluate_report_policy(
            report_obj,
            policy,
            policy_pack=policy_pack,
            policy_file=policy_file,
        )
    except Exception as exc:
        console.print(f"[red]Error evaluating policy: {exc}[/red]")
        raise click.Abort() from exc

    if output_format == "table":
        _print_gate_table(report_obj, evaluation)
        if output:
            Path(output).write_text(
                _format_gate_text(report_file, report_obj, evaluation),
                encoding="utf-8",
            )
            console.print(f"[green]Written to {output}[/green]")
    else:
        content = json.dumps(evaluation, indent=2)
        _output(content, output)

    if not bool(evaluation.get("passed", False)):
        console.print("[red]Gate failed[/red]")
        raise click.exceptions.Exit(2)

    console.print("[green]Gate passed[/green]")


@main.command()
@click.argument("report_files", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "markdown"]),
    default="table",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Optional output file path",
)
def benchmark(report_files: tuple[str, ...], output_format: str, output: Optional[str]) -> None:
    """
    Build advisory benchmark summary from one or more report artifacts.

    Example:
        llm-diff benchmark artifacts/reports/*.json --format table
    """
    if not report_files:
        console.print("[red]At least one report JSON file is required.[/red]")
        raise click.Abort()

    reports = [_load_report(path) for path in report_files]
    try:
        summary = build_benchmark_summary(reports)
    except Exception as exc:
        console.print(f"[red]Error building benchmark summary: {exc}[/red]")
        raise click.Abort() from exc

    summary["source_reports"] = [str(path) for path in report_files]

    if output_format == "table":
        _print_benchmark_table(summary)
        if output:
            Path(output).write_text(
                _format_benchmark_markdown(summary),
                encoding="utf-8",
            )
            console.print(f"[green]Written to {output}[/green]")
        return

    if output_format == "json":
        _output(json.dumps(summary, indent=2), output)
        return

    _output(_format_benchmark_markdown(summary), output)


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


def _print_gate_table(report: BehaviorReport, evaluation: dict[str, Any]) -> None:
    """Print gate result as a rich table."""
    table = Table(title="Risk-Tier Gate Result")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Suite", report.suite_name)
    table.add_row("Policy", str(evaluation.get("policy", "unknown")))
    table.add_row("Policy Pack", str(evaluation.get("policy_pack", "core")))
    table.add_row("Policy Source", str(evaluation.get("policy_source", "builtin:core")))
    table.add_row(
        "Passed",
        "[green]yes[/green]" if bool(evaluation.get("passed")) else "[red]no[/red]",
    )

    observed = evaluation.get("observed", {})
    thresholds = evaluation.get("thresholds", {})
    reasons = evaluation.get("reasons", [])

    if isinstance(observed, dict):
        table.add_row("Total Tests", str(observed.get("total_tests", 0)))
        table.add_row("Regressions", str(observed.get("regressions", 0)))
        regression_by_category = observed.get("regression_by_category", {})
        if isinstance(regression_by_category, dict):
            table.add_row(
                "Regression by Category",
                (
                    json.dumps(regression_by_category, sort_keys=True)
                    if regression_by_category
                    else "{}"
                ),
            )

    if isinstance(thresholds, dict):
        for key, value in thresholds.items():
            label = key.replace("_", " ").title()
            table.add_row(label, json.dumps(value) if isinstance(value, list) else str(value))

    if isinstance(reasons, list):
        table.add_row("Reasons", "\n".join(str(reason) for reason in reasons))

    console.print(table)


def _format_gate_text(report_file: str, report: BehaviorReport, evaluation: dict[str, Any]) -> str:
    """Format gate result as plain markdown-like text."""
    observed = evaluation.get("observed", {})
    thresholds = evaluation.get("thresholds", {})
    reasons = evaluation.get("reasons", [])

    lines = [
        "# Risk-Tier Gate Result",
        "",
        f"- Report: `{report_file}`",
        f"- Suite: `{report.suite_name}`",
        f"- Policy: `{evaluation.get('policy', 'unknown')}`",
        f"- Policy Pack: `{evaluation.get('policy_pack', 'core')}`",
        f"- Policy Source: `{evaluation.get('policy_source', 'builtin:core')}`",
        f"- Passed: `{bool(evaluation.get('passed', False))}`",
    ]

    if isinstance(observed, dict):
        lines.extend(
            [
                f"- Total Tests: {observed.get('total_tests', 0)}",
                f"- Regressions: {observed.get('regressions', 0)}",
                "- Regression by Category: "
                + json.dumps(observed.get("regression_by_category", {}), sort_keys=True),
            ]
        )

    if isinstance(thresholds, dict):
        lines.append("")
        lines.append("## Thresholds")
        for key, value in thresholds.items():
            lines.append(f"- {key}: {value}")

    if isinstance(reasons, list):
        lines.append("")
        lines.append("## Reasons")
        for reason in reasons:
            lines.append(f"- {reason}")

    return "\n".join(lines) + "\n"


def _print_benchmark_table(summary: dict[str, Any]) -> None:
    """Print benchmark summary as rich tables."""
    table = Table(title="Benchmark Summary (Advisory-Only)")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_row("Reports", str(summary.get("total_reports", 0)))
    table.add_row("Total Tests", str(summary.get("total_tests", 0)))
    table.add_row("Processed Tests", str(summary.get("total_processed_tests", 0)))
    table.add_row("Failed Tests", str(summary.get("total_failed_tests", 0)))
    table.add_row("Total Duration (s)", f"{float(summary.get('total_duration_seconds', 0.0)):.4f}")
    table.add_row("Avg Duration (s)", f"{float(summary.get('avg_duration_seconds', 0.0)):.4f}")
    table.add_row(
        "Throughput (tests/min)",
        f"{float(summary.get('throughput_tests_per_min', 0.0)):.4f}",
    )
    table.add_row("Regression Rate (%)", f"{float(summary.get('regression_rate_pct', 0.0)):.4f}")
    table.add_row(
        "Improvement Rate (%)",
        f"{float(summary.get('improvement_rate_pct', 0.0)):.4f}",
    )
    table.add_row(
        "Semantic-Only Rate (%)",
        f"{float(summary.get('semantic_only_rate_pct', 0.0)):.4f}",
    )
    table.add_row("Unknown Rate (%)", f"{float(summary.get('unknown_rate_pct', 0.0)):.4f}")
    critical = summary.get("critical_regressions", {})
    if isinstance(critical, dict):
        table.add_row("Critical safety_boundary", str(critical.get("safety_boundary", 0)))
        table.add_row("Critical hallucination_new", str(critical.get("hallucination_new", 0)))
        table.add_row("Critical format_change", str(critical.get("format_change", 0)))
    console.print(table)

    quality_pack = summary.get("quality_pack", {})
    advisories = quality_pack.get("advisories", []) if isinstance(quality_pack, dict) else []
    if isinstance(advisories, list) and advisories:
        advisory_table = Table(title="Quality Pack Advisories")
        advisory_table.add_column("Code", style="yellow")
        advisory_table.add_column("Message", style="white")
        advisory_table.add_column("Value", style="magenta")
        for advisory in advisories:
            if not isinstance(advisory, dict):
                continue
            advisory_table.add_row(
                str(advisory.get("code", "unknown")),
                str(advisory.get("message", "")),
                json.dumps(advisory.get("value", advisory.get("suites", ""))),
            )
        console.print(advisory_table)
    else:
        console.print("[green]No benchmark advisories triggered.[/green]")

    suites = summary.get("suites", [])
    if isinstance(suites, list):
        suite_table = Table(title="Benchmark Suite Breakdown")
        suite_table.add_column("Suite", style="cyan")
        suite_table.add_column("Tests", justify="right")
        suite_table.add_column("Processed", justify="right")
        suite_table.add_column("Failed", justify="right")
        suite_table.add_column("Duration (s)", justify="right")
        suite_table.add_column("Regressions", justify="right")
        suite_table.add_column("Improvements", justify="right")
        suite_table.add_column("Unknown Rate (%)", justify="right")
        for suite_row in suites:
            if not isinstance(suite_row, dict):
                continue
            suite_table.add_row(
                str(suite_row.get("suite_name", "unknown")),
                str(suite_row.get("total_tests", 0)),
                str(suite_row.get("processed_tests", 0)),
                str(suite_row.get("failed_tests", 0)),
                f"{float(suite_row.get('duration_seconds', 0.0)):.4f}",
                str(suite_row.get("regressions", 0)),
                str(suite_row.get("improvements", 0)),
                f"{float(suite_row.get('unknown_rate_pct', 0.0)):.4f}",
            )
        console.print(suite_table)


def _format_benchmark_markdown(summary: dict[str, Any]) -> str:
    """Format benchmark summary as markdown."""
    quality_pack = summary.get("quality_pack", {})
    advisories = quality_pack.get("advisories", []) if isinstance(quality_pack, dict) else []
    source_reports = summary.get("source_reports", [])

    lines = [
        "# Benchmark Summary",
        "",
        "- Mode: advisory-only",
        f"- Reports: {summary.get('total_reports', 0)}",
        f"- Total Tests: {summary.get('total_tests', 0)}",
        f"- Processed Tests: {summary.get('total_processed_tests', 0)}",
        f"- Failed Tests: {summary.get('total_failed_tests', 0)}",
        f"- Total Duration (s): {float(summary.get('total_duration_seconds', 0.0)):.4f}",
        f"- Avg Duration (s): {float(summary.get('avg_duration_seconds', 0.0)):.4f}",
        f"- Throughput (tests/min): {float(summary.get('throughput_tests_per_min', 0.0)):.4f}",
        f"- Regression Rate (%): {float(summary.get('regression_rate_pct', 0.0)):.4f}",
        f"- Improvement Rate (%): {float(summary.get('improvement_rate_pct', 0.0)):.4f}",
        f"- Semantic-Only Rate (%): {float(summary.get('semantic_only_rate_pct', 0.0)):.4f}",
        f"- Unknown Rate (%): {float(summary.get('unknown_rate_pct', 0.0)):.4f}",
    ]

    critical = summary.get("critical_regressions", {})
    if isinstance(critical, dict):
        lines.extend(
            [
                "- Critical Regressions:",
                f"  - safety_boundary: {critical.get('safety_boundary', 0)}",
                f"  - hallucination_new: {critical.get('hallucination_new', 0)}",
                f"  - format_change: {critical.get('format_change', 0)}",
            ]
        )

    if isinstance(source_reports, list) and source_reports:
        lines.append("")
        lines.append("## Source Reports")
        for path in source_reports:
            lines.append(f"- `{path}`")

    lines.append("")
    lines.append("## Advisories")
    if isinstance(advisories, list) and advisories:
        for advisory in advisories:
            if not isinstance(advisory, dict):
                continue
            code = str(advisory.get("code", "unknown"))
            message = str(advisory.get("message", ""))
            value = advisory.get("value", advisory.get("suites", ""))
            lines.append(f"- `{code}`: {message} ({value})")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Suite Breakdown",
            "",
            "| Suite | Tests | Processed | Failed | Duration (s) | Regressions | Improvements | Unknown Rate (%) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    suites = summary.get("suites", [])
    if isinstance(suites, list):
        for suite_row in suites:
            if not isinstance(suite_row, dict):
                continue
            lines.append(
                "| "
                + f"{suite_row.get('suite_name', 'unknown')} | "
                + f"{suite_row.get('total_tests', 0)} | "
                + f"{suite_row.get('processed_tests', 0)} | "
                + f"{suite_row.get('failed_tests', 0)} | "
                + f"{float(suite_row.get('duration_seconds', 0.0)):.4f} | "
                + f"{suite_row.get('regressions', 0)} | "
                + f"{suite_row.get('improvements', 0)} | "
                + f"{float(suite_row.get('unknown_rate_pct', 0.0)):.4f} |"
            )

    return "\n".join(lines) + "\n"


def _behavior_category_value(raw_category: Any) -> str:
    if hasattr(raw_category, "value"):
        return str(raw_category.value)
    return str(raw_category)


def _diff_status(result: Any) -> str:
    if bool(result.is_regression):
        return "regression"
    if bool(result.is_improvement):
        return "improvement"
    if bool(result.is_semantically_same) and result.response_a.strip() != result.response_b.strip():
        return "semantic-only"
    if (
        not bool(result.is_semantically_same)
        and not bool(result.is_regression)
        and not bool(result.is_improvement)
    ):
        return "unknown"
    return "other"


def _format_csv(report: BehaviorReport) -> str:
    """Format report diff rows as CSV (metric-focused, no raw responses)."""
    fieldnames = [
        "report_id",
        "suite_name",
        "model_a",
        "model_b",
        "test_id",
        "behavior_category",
        "status",
        "is_semantically_same",
        "semantic_similarity",
        "is_regression",
        "is_improvement",
        "confidence",
        "explanation",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()

    for result in report.diff_results:
        writer.writerow(
            {
                "report_id": report.id,
                "suite_name": report.suite_name,
                "model_a": report.model_a,
                "model_b": report.model_b,
                "test_id": result.test_id,
                "behavior_category": _behavior_category_value(result.behavior_category),
                "status": _diff_status(result),
                "is_semantically_same": bool(result.is_semantically_same),
                "semantic_similarity": float(result.semantic_similarity),
                "is_regression": bool(result.is_regression),
                "is_improvement": bool(result.is_improvement),
                "confidence": float(result.confidence),
                "explanation": result.explanation,
            }
        )

    return buffer.getvalue()


def _format_ndjson(report: BehaviorReport) -> str:
    """Format report diff rows as NDJSON including raw responses and comparator metadata."""
    lines: list[str] = []
    for result in report.diff_results:
        payload = {
            "report_id": report.id,
            "suite_name": report.suite_name,
            "model_a": report.model_a,
            "model_b": report.model_b,
            "test_id": result.test_id,
            "behavior_category": _behavior_category_value(result.behavior_category),
            "status": _diff_status(result),
            "is_semantically_same": bool(result.is_semantically_same),
            "semantic_similarity": float(result.semantic_similarity),
            "is_regression": bool(result.is_regression),
            "is_improvement": bool(result.is_improvement),
            "confidence": float(result.confidence),
            "explanation": result.explanation,
            "response_a": result.response_a,
            "response_b": result.response_b,
            "metadata": result.metadata,
        }
        lines.append(json.dumps(payload, ensure_ascii=False, default=str))
    return ("\n".join(lines) + "\n") if lines else ""


def _format_junit(report: BehaviorReport) -> str:
    """Format report diff rows as JUnit XML."""
    testsuite = ET.Element(
        "testsuite",
        attrib={
            "name": report.suite_name,
            "tests": str(len(report.diff_results)),
            "failures": str(sum(1 for result in report.diff_results if result.is_regression)),
            "errors": "0",
            "skipped": "0",
        },
    )

    properties = ET.SubElement(testsuite, "properties")
    ET.SubElement(properties, "property", name="report_id", value=str(report.id))
    ET.SubElement(properties, "property", name="model_a", value=report.model_a)
    ET.SubElement(properties, "property", name="model_b", value=report.model_b)
    ET.SubElement(properties, "property", name="total_tests", value=str(report.total_tests))
    ET.SubElement(properties, "property", name="total_diffs", value=str(report.total_diffs))
    ET.SubElement(properties, "property", name="regressions", value=str(report.regressions))
    ET.SubElement(properties, "property", name="improvements", value=str(report.improvements))

    for result in report.diff_results:
        status = _diff_status(result)
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            attrib={
                "classname": report.suite_name,
                "name": result.test_id,
            },
        )
        if bool(result.is_regression):
            failure = ET.SubElement(
                testcase,
                "failure",
                attrib={
                    "message": "Regression detected",
                    "type": _behavior_category_value(result.behavior_category),
                },
            )
            failure.text = result.explanation or "Regression detected by deterministic comparator."

        system_out = ET.SubElement(testcase, "system-out")
        system_out.text = (
            f"status={status}; category={_behavior_category_value(result.behavior_category)}; "
            f"semantic_similarity={float(result.semantic_similarity):.4f}; "
            f"confidence={float(result.confidence):.4f}; "
            f"is_regression={bool(result.is_regression)}; "
            f"is_improvement={bool(result.is_improvement)}"
        )

    xml_payload = ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    if isinstance(xml_payload, bytes):
        return xml_payload.decode("utf-8")
    return str(xml_payload)


def _resolve_export_api_key(explicit_api_key: Optional[str]) -> Optional[str]:
    if explicit_api_key and explicit_api_key.strip():
        return explicit_api_key.strip()
    env_api_key = os.getenv("LLM_DIFF_EXPORT_API_KEY", "").strip()
    return env_api_key or None


def _resolve_export_snowflake_password(explicit_password: Optional[str]) -> Optional[str]:
    if explicit_password and explicit_password.strip():
        return explicit_password.strip()
    env_password = os.getenv("LLM_DIFF_EXPORT_SF_PASSWORD", "").strip()
    return env_password or None


def _resolve_export_redshift_password(explicit_password: Optional[str]) -> Optional[str]:
    if explicit_password and explicit_password.strip():
        return explicit_password.strip()
    env_password = os.getenv("LLM_DIFF_EXPORT_RS_PASSWORD", "").strip()
    return env_password or None


def _resolve_export_databricks_token(explicit_token: Optional[str]) -> Optional[str]:
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()
    env_token = os.getenv("LLM_DIFF_EXPORT_DBX_TOKEN", "").strip()
    return env_token or None


def _content_type_for_report_format(report_format: str) -> str:
    mapping = {
        "json": "application/json",
        "html": "text/html",
        "markdown": "text/markdown",
        "csv": "text/csv",
        "ndjson": "application/x-ndjson",
        "junit": "application/xml",
    }
    return mapping.get(report_format, "text/plain")


def _extension_for_report_format(report_format: str) -> str:
    mapping = {
        "json": "json",
        "html": "html",
        "markdown": "md",
        "csv": "csv",
        "ndjson": "ndjson",
        "junit": "xml",
    }
    return mapping.get(report_format, "txt")


def _build_s3_object_key(prefix: str, suite_name: str, report_id: str, report_format: str) -> str:
    normalized_prefix = prefix.strip()
    if normalized_prefix:
        normalized_prefix = normalized_prefix.strip("/")
        normalized_prefix = f"{normalized_prefix}/"
    extension = _extension_for_report_format(report_format)
    return f"{normalized_prefix}{suite_name}/{report_id}/report.{extension}"


def _create_s3_client(region: Optional[str], timeout_seconds: float) -> Any:
    import boto3
    from botocore.config import Config

    kwargs: dict[str, Any] = {
        "config": Config(
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            retries={"max_attempts": 1},
        )
    }
    if region and region.strip():
        kwargs["region_name"] = region.strip()
    return boto3.client("s3", **kwargs)


def _build_gcs_object_key(prefix: str, suite_name: str, report_id: str, report_format: str) -> str:
    return _build_s3_object_key(
        prefix=prefix,
        suite_name=suite_name,
        report_id=report_id,
        report_format=report_format,
    )


def _create_gcs_client(project: Optional[str], timeout_seconds: float) -> Any:
    from google.cloud.storage import Client

    _ = timeout_seconds
    kwargs: dict[str, Any] = {}
    if project and project.strip():
        kwargs["project"] = project.strip()
    return Client(**kwargs)


def _build_azure_blob_object_key(
    prefix: str, suite_name: str, report_id: str, report_format: str
) -> str:
    return _build_s3_object_key(
        prefix=prefix,
        suite_name=suite_name,
        report_id=report_id,
        report_format=report_format,
    )


def _create_azure_blob_service_client(account_url: str, timeout_seconds: float) -> Any:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    _ = timeout_seconds
    credential = DefaultAzureCredential()
    return BlobServiceClient(account_url=account_url, credential=credential)


def _create_bigquery_client(project: str, location: Optional[str]) -> Any:
    from google.cloud import bigquery

    kwargs: dict[str, Any] = {"project": project.strip()}
    if location and location.strip():
        kwargs["location"] = location.strip()
    return bigquery.Client(**kwargs)


def _create_snowflake_connection(
    *,
    account: str,
    user: str,
    password: str,
    warehouse: str,
    database: str,
    schema: str,
    role: Optional[str],
    timeout_seconds: float,
) -> Any:
    import snowflake.connector

    kwargs: dict[str, Any] = {
        "account": account,
        "user": user,
        "password": password,
        "warehouse": warehouse,
        "database": database,
        "schema": schema,
        "login_timeout": max(1, int(round(timeout_seconds))),
        "network_timeout": timeout_seconds,
    }
    if role and role.strip():
        kwargs["role"] = role.strip()
    return snowflake.connector.connect(**kwargs)


def _create_redshift_connection(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    sslmode: str,
    timeout_seconds: float,
) -> Any:
    import redshift_connector

    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
        "sslmode": sslmode,
        "timeout": timeout_seconds,
    }
    try:
        return redshift_connector.connect(**kwargs)
    except TypeError:
        kwargs.pop("timeout", None)
        return redshift_connector.connect(**kwargs)


def _normalize_databricks_host(host: str) -> str:
    normalized = host.strip()
    if not normalized:
        raise ValueError("Databricks host must not be empty.")

    if "://" in normalized:
        parsed = urlparse(normalized)
        normalized = parsed.netloc or parsed.path

    normalized = normalized.strip().strip("/")
    if "/" in normalized:
        normalized = normalized.split("/", 1)[0]

    if not normalized:
        raise ValueError("Databricks host must not be empty.")
    return normalized


def _create_databricks_connection(
    *,
    host: str,
    http_path: str,
    token: str,
    timeout_seconds: float,
) -> Any:
    from databricks import sql

    _ = timeout_seconds
    return sql.connect(
        server_hostname=_normalize_databricks_host(host),
        http_path=http_path.strip(),
        access_token=token,
    )


def _quote_snowflake_identifier(identifier: str) -> str:
    normalized = identifier.strip()
    if not normalized:
        raise ValueError("Snowflake identifier must not be empty.")
    escaped = normalized.replace('"', '""')
    return f'"{escaped}"'


def _quote_redshift_identifier(identifier: str) -> str:
    normalized = identifier.strip()
    if not normalized:
        raise ValueError("Redshift identifier must not be empty.")
    escaped = normalized.replace('"', '""')
    return f'"{escaped}"'


def _quote_databricks_identifier(identifier: str) -> str:
    normalized = identifier.strip()
    if not normalized:
        raise ValueError("Databricks identifier must not be empty.")
    escaped = normalized.replace('"', '""')
    return f'"{escaped}"'


def _build_bigquery_rows_from_ndjson(content: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        raw_line = line.strip()
        if not raw_line:
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid NDJSON row at line {line_number}: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid NDJSON row at line {line_number}: expected JSON object")

        metadata_payload = payload.get("metadata", {})
        row = {
            "report_id": str(payload.get("report_id", "")),
            "suite_name": str(payload.get("suite_name", "")),
            "model_a": str(payload.get("model_a", "")),
            "model_b": str(payload.get("model_b", "")),
            "test_id": str(payload.get("test_id", "")),
            "behavior_category": str(payload.get("behavior_category", "")),
            "status": str(payload.get("status", "")),
            "is_semantically_same": bool(payload.get("is_semantically_same", False)),
            "semantic_similarity": float(payload.get("semantic_similarity", 0.0)),
            "is_regression": bool(payload.get("is_regression", False)),
            "is_improvement": bool(payload.get("is_improvement", False)),
            "confidence": float(payload.get("confidence", 0.0)),
            "explanation": str(payload.get("explanation", "")),
            "response_a": str(payload.get("response_a", "")),
            "response_b": str(payload.get("response_b", "")),
            "metadata_json": json.dumps(
                metadata_payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        }
        rows.append(row)
    return rows


def _dispatch_report_export(
    report: BehaviorReport,
    report_format: str,
    content: str,
    connector: str,
    endpoint: Optional[str],
    timeout_seconds: float,
    api_key: Optional[str],
    s3_bucket: Optional[str],
    s3_prefix: str,
    s3_region: Optional[str],
    gcs_bucket: Optional[str],
    gcs_prefix: str,
    gcs_project: Optional[str],
    az_account_url: Optional[str],
    az_container: Optional[str],
    az_prefix: str,
    bq_project: Optional[str],
    bq_dataset: Optional[str],
    bq_table: Optional[str],
    bq_location: Optional[str],
    sf_account: Optional[str],
    sf_user: Optional[str],
    sf_password: Optional[str],
    sf_role: Optional[str],
    sf_warehouse: Optional[str],
    sf_database: Optional[str],
    sf_schema: Optional[str],
    sf_table: Optional[str],
    rs_host: Optional[str],
    rs_port: int,
    rs_database: Optional[str],
    rs_user: Optional[str],
    rs_password: Optional[str],
    rs_schema: Optional[str],
    rs_table: Optional[str],
    rs_sslmode: str,
    dbx_host: Optional[str],
    dbx_http_path: Optional[str],
    dbx_token: Optional[str],
    dbx_catalog: Optional[str],
    dbx_schema: Optional[str],
    dbx_table: Optional[str],
) -> None:
    if timeout_seconds <= 0:
        raise ValueError("export_timeout must be > 0")

    normalized = connector.strip().lower()
    if normalized == "none":
        return
    if normalized == "http":
        if not endpoint or not endpoint.strip():
            raise ValueError("export_endpoint is required when export_connector is 'http'.")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "llm-behavior-diff/0.1 report-export",
        }
        resolved_api_key = _resolve_export_api_key(api_key)
        if resolved_api_key:
            headers["Authorization"] = f"Bearer {resolved_api_key}"

        payload = {
            "event": "llm_behavior_diff_report_export",
            "report": {
                "id": report.id,
                "suite_name": report.suite_name,
                "model_a": report.model_a,
                "model_b": report.model_b,
                "total_tests": report.total_tests,
                "total_diffs": report.total_diffs,
                "regressions": report.regressions,
                "improvements": report.improvements,
            },
            "export": {
                "format": report_format,
                "content_type": _content_type_for_report_format(report_format),
                "content": content,
            },
        }

        response = httpx.post(
            endpoint.strip(),
            json=payload,
            headers=headers,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return

    if normalized == "s3":
        if not s3_bucket or not s3_bucket.strip():
            raise ValueError("export_s3_bucket is required when export_connector is 's3'.")
        object_key = _build_s3_object_key(
            prefix=s3_prefix,
            suite_name=report.suite_name,
            report_id=str(report.id),
            report_format=report_format,
        )
        client = _create_s3_client(region=s3_region, timeout_seconds=timeout_seconds)
        client.put_object(
            Bucket=s3_bucket.strip(),
            Key=object_key,
            Body=content.encode("utf-8"),
            ContentType=_content_type_for_report_format(report_format),
        )
        return

    if normalized == "gcs":
        if not gcs_bucket or not gcs_bucket.strip():
            raise ValueError("export_gcs_bucket is required when export_connector is 'gcs'.")
        object_key = _build_gcs_object_key(
            prefix=gcs_prefix,
            suite_name=report.suite_name,
            report_id=str(report.id),
            report_format=report_format,
        )
        client = _create_gcs_client(project=gcs_project, timeout_seconds=timeout_seconds)
        bucket = client.bucket(gcs_bucket.strip())
        blob = bucket.blob(object_key)
        blob.upload_from_string(
            content,
            content_type=_content_type_for_report_format(report_format),
            timeout=timeout_seconds,
        )
        return

    if normalized == "azure_blob":
        if not az_account_url or not az_account_url.strip():
            raise ValueError(
                "export_az_account_url is required when export_connector is 'azure_blob'."
            )
        if not az_container or not az_container.strip():
            raise ValueError(
                "export_az_container is required when export_connector is 'azure_blob'."
            )
        object_key = _build_azure_blob_object_key(
            prefix=az_prefix,
            suite_name=report.suite_name,
            report_id=str(report.id),
            report_format=report_format,
        )
        service_client = _create_azure_blob_service_client(
            account_url=az_account_url.strip(),
            timeout_seconds=timeout_seconds,
        )
        blob_client = service_client.get_blob_client(
            container=az_container.strip(),
            blob=object_key,
        )
        blob_client.upload_blob(
            content.encode("utf-8"),
            overwrite=True,
            content_type=_content_type_for_report_format(report_format),
            timeout=timeout_seconds,
        )
        return

    if normalized == "bigquery":
        if report_format != "ndjson":
            raise ValueError("export_connector 'bigquery' supports only --format ndjson.")
        if not bq_project or not bq_project.strip():
            raise ValueError("export_bq_project is required when export_connector is 'bigquery'.")
        if not bq_dataset or not bq_dataset.strip():
            raise ValueError("export_bq_dataset is required when export_connector is 'bigquery'.")
        if not bq_table or not bq_table.strip():
            raise ValueError("export_bq_table is required when export_connector is 'bigquery'.")

        rows = _build_bigquery_rows_from_ndjson(content)
        if not rows:
            return

        project = bq_project.strip()
        dataset = bq_dataset.strip()
        table = bq_table.strip()
        table_id = f"{project}.{dataset}.{table}"
        client = _create_bigquery_client(project=project, location=bq_location)
        errors = client.insert_rows_json(table_id, rows, timeout=timeout_seconds)
        if errors:
            raise RuntimeError(f"BigQuery insert failed for table '{table_id}': {errors}")
        return

    if normalized == "snowflake":
        if report_format != "ndjson":
            raise ValueError("export_connector 'snowflake' supports only --format ndjson.")
        if not sf_account or not sf_account.strip():
            raise ValueError("export_sf_account is required when export_connector is 'snowflake'.")
        if not sf_user or not sf_user.strip():
            raise ValueError("export_sf_user is required when export_connector is 'snowflake'.")
        resolved_password = _resolve_export_snowflake_password(sf_password)
        if not resolved_password:
            raise ValueError(
                "Snowflake password is required via --export-sf-password or "
                "LLM_DIFF_EXPORT_SF_PASSWORD."
            )
        if not sf_warehouse or not sf_warehouse.strip():
            raise ValueError(
                "export_sf_warehouse is required when export_connector is 'snowflake'."
            )
        if not sf_database or not sf_database.strip():
            raise ValueError("export_sf_database is required when export_connector is 'snowflake'.")
        if not sf_schema or not sf_schema.strip():
            raise ValueError("export_sf_schema is required when export_connector is 'snowflake'.")
        if not sf_table or not sf_table.strip():
            raise ValueError("export_sf_table is required when export_connector is 'snowflake'.")

        rows = _build_bigquery_rows_from_ndjson(content)
        if not rows:
            return

        account = sf_account.strip()
        user = sf_user.strip()
        warehouse = sf_warehouse.strip()
        database = sf_database.strip()
        schema = sf_schema.strip()
        table = sf_table.strip()
        quoted_table = ".".join(
            [
                _quote_snowflake_identifier(database),
                _quote_snowflake_identifier(schema),
                _quote_snowflake_identifier(table),
            ]
        )
        columns = list(rows[0].keys())
        quoted_columns = ", ".join(_quote_snowflake_identifier(column) for column in columns)
        placeholders = ", ".join(f"%({column})s" for column in columns)
        query = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"
        connection = _create_snowflake_connection(
            account=account,
            user=user,
            password=resolved_password,
            warehouse=warehouse,
            database=database,
            schema=schema,
            role=sf_role,
            timeout_seconds=timeout_seconds,
        )
        cursor = connection.cursor()
        try:
            cursor.executemany(query, rows)
            connection.commit()
        finally:
            cursor.close()
            connection.close()
        return

    if normalized == "redshift":
        if report_format != "ndjson":
            raise ValueError("export_connector 'redshift' supports only --format ndjson.")
        if not rs_host or not rs_host.strip():
            raise ValueError("export_rs_host is required when export_connector is 'redshift'.")
        if rs_port <= 0:
            raise ValueError("export_rs_port must be > 0 when export_connector is 'redshift'.")
        if not rs_database or not rs_database.strip():
            raise ValueError("export_rs_database is required when export_connector is 'redshift'.")
        if not rs_user or not rs_user.strip():
            raise ValueError("export_rs_user is required when export_connector is 'redshift'.")
        resolved_rs_password = _resolve_export_redshift_password(rs_password)
        if not resolved_rs_password:
            raise ValueError(
                "Redshift password is required via --export-rs-password or "
                "LLM_DIFF_EXPORT_RS_PASSWORD."
            )
        if not rs_schema or not rs_schema.strip():
            raise ValueError("export_rs_schema is required when export_connector is 'redshift'.")
        if not rs_table or not rs_table.strip():
            raise ValueError("export_rs_table is required when export_connector is 'redshift'.")
        if not rs_sslmode or not rs_sslmode.strip():
            raise ValueError(
                "export_rs_sslmode must not be empty when export_connector is 'redshift'."
            )

        rows = _build_bigquery_rows_from_ndjson(content)
        if not rows:
            return

        quoted_table = ".".join(
            [
                _quote_redshift_identifier(rs_schema),
                _quote_redshift_identifier(rs_table),
            ]
        )
        columns = list(rows[0].keys())
        quoted_columns = ", ".join(_quote_redshift_identifier(column) for column in columns)
        placeholders = ", ".join(f"%({column})s" for column in columns)
        query = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"
        connection = _create_redshift_connection(
            host=rs_host.strip(),
            port=rs_port,
            database=rs_database.strip(),
            user=rs_user.strip(),
            password=resolved_rs_password,
            sslmode=rs_sslmode.strip(),
            timeout_seconds=timeout_seconds,
        )
        cursor = connection.cursor()
        try:
            cursor.executemany(query, rows)
            connection.commit()
        finally:
            cursor.close()
            connection.close()
        return

    if normalized == "databricks":
        if report_format != "ndjson":
            raise ValueError("export_connector 'databricks' supports only --format ndjson.")
        if not dbx_host or not dbx_host.strip():
            raise ValueError("export_dbx_host is required when export_connector is 'databricks'.")
        if not dbx_http_path or not dbx_http_path.strip():
            raise ValueError(
                "export_dbx_http_path is required when export_connector is 'databricks'."
            )
        resolved_dbx_token = _resolve_export_databricks_token(dbx_token)
        if not resolved_dbx_token:
            raise ValueError(
                "Databricks token is required via --export-dbx-token or "
                "LLM_DIFF_EXPORT_DBX_TOKEN."
            )
        if not dbx_catalog or not dbx_catalog.strip():
            raise ValueError(
                "export_dbx_catalog is required when export_connector is 'databricks'."
            )
        if not dbx_schema or not dbx_schema.strip():
            raise ValueError("export_dbx_schema is required when export_connector is 'databricks'.")
        if not dbx_table or not dbx_table.strip():
            raise ValueError("export_dbx_table is required when export_connector is 'databricks'.")

        rows = _build_bigquery_rows_from_ndjson(content)
        if not rows:
            return

        quoted_table = ".".join(
            [
                _quote_databricks_identifier(dbx_catalog),
                _quote_databricks_identifier(dbx_schema),
                _quote_databricks_identifier(dbx_table),
            ]
        )
        columns = list(rows[0].keys())
        quoted_columns = ", ".join(_quote_databricks_identifier(column) for column in columns)
        placeholders = ", ".join(f"%({column})s" for column in columns)
        query = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"
        connection = _create_databricks_connection(
            host=dbx_host,
            http_path=dbx_http_path,
            token=resolved_dbx_token,
            timeout_seconds=timeout_seconds,
        )
        cursor = connection.cursor()
        try:
            cursor.executemany(query, rows)
            connection.commit()
        finally:
            cursor.close()
            connection.close()
        return

    raise ValueError(
        f"Unsupported export connector '{connector}'. Supported: none, http, s3, gcs, "
        "bigquery, snowflake, redshift, azure_blob, databricks."
    )


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
