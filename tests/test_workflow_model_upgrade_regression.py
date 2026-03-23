"""Workflow guard for model-upgrade regression connector inputs/wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "model-upgrade-regression.yml"


def _load_workflow() -> dict[str, Any]:
    payload = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8")) or {}
    assert isinstance(payload, dict), "Workflow YAML must be a top-level mapping."
    return payload


def _assert_input_present(inputs: dict[str, Any], key: str) -> None:
    assert key in inputs, f"Missing '{key}' input in workflow."


def test_model_upgrade_workflow_has_factual_connector_inputs_and_export_wiring() -> None:
    workflow = _load_workflow()
    on_section = workflow.get("on", workflow.get(True))
    assert isinstance(on_section, dict), "Workflow must define an 'on' section."

    dispatch_inputs = on_section["workflow_dispatch"]["inputs"]
    call_inputs = on_section["workflow_call"]["inputs"]
    assert isinstance(dispatch_inputs, dict)
    assert isinstance(call_inputs, dict)

    for key in (
        "factual_connector",
        "factual_connector_timeout",
        "factual_connector_max_results",
        "export_connector",
        "export_connector_endpoint",
        "export_connector_timeout",
        "export_s3_bucket",
        "export_s3_prefix",
        "export_s3_region",
        "export_bq_project",
        "export_bq_dataset",
        "export_bq_table",
        "export_bq_location",
        "export_sf_account",
        "export_sf_user",
        "export_sf_role",
        "export_sf_warehouse",
        "export_sf_database",
        "export_sf_schema",
        "export_sf_table",
    ):
        _assert_input_present(dispatch_inputs, key)
        _assert_input_present(call_inputs, key)

    steps = workflow["jobs"]["regression-gate"]["steps"]
    assert isinstance(steps, list)
    run_step = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Run behavioral diff suites"
    )
    run_script = str(run_step.get("run", ""))
    assert '--factual-connector "$FACTUAL_CONNECTOR"' in run_script
    assert '--factual-connector-timeout "$FACTUAL_CONNECTOR_TIMEOUT"' in run_script
    assert '--factual-connector-max-results "$FACTUAL_CONNECTOR_MAX_RESULTS"' in run_script
    assert (
        'llm-diff report "$output_file" --format csv --output "artifacts/exports/${suite_name}.csv"'
        in run_script
    )
    assert (
        'llm-diff report "$output_file" --format ndjson --output "artifacts/exports/${suite_name}.ndjson"'
        in run_script
    )
    assert (
        'llm-diff report "$output_file" --format junit --output "artifacts/exports/${suite_name}.junit.xml"'
        in run_script
    )
    assert '--export-connector "$EXPORT_CONNECTOR"' in run_script
    assert '--export-timeout "$EXPORT_CONNECTOR_TIMEOUT"' in run_script
    assert '--export-endpoint "$EXPORT_CONNECTOR_ENDPOINT"' in run_script
    assert '--export-s3-bucket "$EXPORT_S3_BUCKET"' in run_script
    assert '--export-s3-prefix "$EXPORT_S3_PREFIX"' in run_script
    assert '--export-s3-region "$EXPORT_S3_REGION"' in run_script
    assert '--export-bq-project "$EXPORT_BQ_PROJECT"' in run_script
    assert '--export-bq-dataset "$EXPORT_BQ_DATASET"' in run_script
    assert '--export-bq-table "$EXPORT_BQ_TABLE"' in run_script
    assert '--export-bq-location "$EXPORT_BQ_LOCATION"' in run_script
    assert '--export-sf-account "$EXPORT_SF_ACCOUNT"' in run_script
    assert '--export-sf-user "$EXPORT_SF_USER"' in run_script
    assert '--export-sf-warehouse "$EXPORT_SF_WAREHOUSE"' in run_script
    assert '--export-sf-database "$EXPORT_SF_DATABASE"' in run_script
    assert '--export-sf-schema "$EXPORT_SF_SCHEMA"' in run_script
    assert '--export-sf-table "$EXPORT_SF_TABLE"' in run_script
    assert '--export-sf-role "$EXPORT_SF_ROLE"' in run_script
    assert "SNOWFLAKE_PASSWORD secret is required when export_connector=snowflake." in run_script
    assert 'elif [ "$EXPORT_CONNECTOR" = "bigquery" ]; then' in run_script
    assert 'elif [ "$EXPORT_CONNECTOR" = "snowflake" ]; then' in run_script

    export_step = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Upload suite exports"
    )
    assert export_step.get("uses") == (
        "actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f"
    )
    export_with = export_step.get("with")
    assert isinstance(export_with, dict)
    assert export_with.get("path") == "artifacts/exports/"
