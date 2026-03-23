"""Workflow guard for model-upgrade regression connector inputs/wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from yaml.resolver import BaseResolver  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "model-upgrade-regression.yml"

EXPECTED_INPUT_KEYS = (
    "factual_connector",
    "factual_connector_max_results",
    "factual_connector_timeout",
    "export_bq_dataset",
    "export_bq_location",
    "export_bq_project",
    "export_bq_table",
    "export_connector",
    "export_connector_endpoint",
    "export_connector_timeout",
    "export_s3_bucket",
    "export_s3_prefix",
    "export_sf_account",
    "export_sf_database",
    "export_sf_schema",
    "export_sf_table",
    "export_sf_user",
    "export_sf_warehouse",
    "gate_policy",
    "gate_policy_file",
    "gate_policy_pack",
    "max_workers",
    "model_a",
    "model_b",
    "suite_list",
)


class _NoDuplicateKeyLoader(yaml.SafeLoader):
    """YAML loader that fails hard on duplicate mapping keys."""


def _construct_mapping_no_duplicates(
    loader: _NoDuplicateKeyLoader,
    node: yaml.nodes.MappingNode,  # type: ignore[name-defined]
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            line = key_node.start_mark.line + 1
            raise AssertionError(
                f"Duplicate YAML key '{key}' in {WORKFLOW_PATH.name} at line {line}."
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeyLoader.add_constructor(  # type: ignore[arg-type]
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


def _load_workflow() -> dict[str, Any]:
    payload = (
        yaml.load(
            WORKFLOW_PATH.read_text(encoding="utf-8"),
            Loader=_NoDuplicateKeyLoader,
        )
        or {}
    )
    assert isinstance(payload, dict), "Workflow YAML must be a top-level mapping."
    return payload


def _assert_input_present(inputs: dict[str, Any], key: str) -> None:
    assert key in inputs, f"Missing '{key}' input in workflow."


def _assert_input_shape(inputs: dict[str, Any], source: str) -> None:
    assert len(inputs) <= 25, (
        f"{source} input count exceeds GitHub Actions workflow input limit (25): " f"{len(inputs)}"
    )
    assert set(inputs) == set(EXPECTED_INPUT_KEYS), (
        f"{source} input keys drifted.\n"
        f"Expected: {sorted(EXPECTED_INPUT_KEYS)}\n"
        f"Actual: {sorted(inputs)}"
    )
    for key, value in inputs.items():
        assert isinstance(value, dict), f"'{key}' in {source} must be a mapping."
        assert isinstance(
            value.get("required"), bool
        ), f"'{key}' in {source} must define boolean 'required'."
        assert isinstance(value.get("type"), str), f"'{key}' in {source} must define string 'type'."


def test_model_upgrade_workflow_has_factual_connector_inputs_and_export_wiring() -> None:
    workflow = _load_workflow()
    on_section = workflow.get("on", workflow.get(True))
    assert isinstance(on_section, dict), "Workflow must define an 'on' section."
    assert set(on_section) == {"workflow_dispatch", "workflow_call"}, (
        "model-upgrade-regression.yml must remain manual/reusable only " "(no push trigger)."
    )

    dispatch_inputs = on_section["workflow_dispatch"]["inputs"]
    call_inputs = on_section["workflow_call"]["inputs"]
    call_secrets = on_section["workflow_call"]["secrets"]
    assert isinstance(dispatch_inputs, dict)
    assert isinstance(call_inputs, dict)
    assert isinstance(call_secrets, dict)
    _assert_input_shape(dispatch_inputs, "workflow_dispatch")
    _assert_input_shape(call_inputs, "workflow_call")

    for key in EXPECTED_INPUT_KEYS:
        _assert_input_present(dispatch_inputs, key)
        _assert_input_present(call_inputs, key)

    export_connector = dispatch_inputs["export_connector"]
    assert isinstance(export_connector, dict)
    options = export_connector.get("options")
    assert isinstance(options, list)
    assert "gcs" in options
    assert "redshift" in options
    assert "azure_blob" in options

    job_env = workflow["jobs"]["regression-gate"]["env"]
    assert isinstance(job_env, dict)
    assert job_env.get("EXPORT_GCS_BUCKET") == "${{ vars.EXPORT_GCS_BUCKET }}"
    assert job_env.get("EXPORT_GCS_PREFIX") == "${{ vars.EXPORT_GCS_PREFIX }}"
    assert job_env.get("EXPORT_GCS_PROJECT") == "${{ vars.EXPORT_GCS_PROJECT }}"
    assert job_env.get("EXPORT_AZ_ACCOUNT_URL") == "${{ vars.EXPORT_AZ_ACCOUNT_URL }}"
    assert job_env.get("EXPORT_AZ_CONTAINER") == "${{ vars.EXPORT_AZ_CONTAINER }}"
    assert job_env.get("EXPORT_AZ_PREFIX") == "${{ vars.EXPORT_AZ_PREFIX }}"
    assert job_env.get("EXPORT_RS_HOST") == "${{ vars.EXPORT_RS_HOST }}"
    assert job_env.get("EXPORT_RS_PORT") == "${{ vars.EXPORT_RS_PORT }}"
    assert job_env.get("EXPORT_RS_DATABASE") == "${{ vars.EXPORT_RS_DATABASE }}"
    assert job_env.get("EXPORT_RS_USER") == "${{ vars.EXPORT_RS_USER }}"
    assert job_env.get("EXPORT_RS_SCHEMA") == "${{ vars.EXPORT_RS_SCHEMA }}"
    assert job_env.get("EXPORT_RS_TABLE") == "${{ vars.EXPORT_RS_TABLE }}"
    assert job_env.get("EXPORT_RS_SSLMODE") == "${{ vars.EXPORT_RS_SSLMODE }}"
    assert job_env.get("LLM_DIFF_EXPORT_RS_PASSWORD") == "${{ secrets.REDSHIFT_PASSWORD }}"

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
    assert '--export-gcs-bucket "$EXPORT_GCS_BUCKET"' in run_script
    assert '--export-gcs-prefix "${EXPORT_GCS_PREFIX:-}"' in run_script
    assert '--export-gcs-project "$EXPORT_GCS_PROJECT"' in run_script
    assert '--export-az-account-url "$EXPORT_AZ_ACCOUNT_URL"' in run_script
    assert '--export-az-container "$EXPORT_AZ_CONTAINER"' in run_script
    assert '--export-az-prefix "${EXPORT_AZ_PREFIX:-}"' in run_script
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
    assert '--export-rs-host "$EXPORT_RS_HOST"' in run_script
    assert '--export-rs-port "${EXPORT_RS_PORT:-5439}"' in run_script
    assert '--export-rs-database "$EXPORT_RS_DATABASE"' in run_script
    assert '--export-rs-user "$EXPORT_RS_USER"' in run_script
    assert '--export-rs-schema "$EXPORT_RS_SCHEMA"' in run_script
    assert '--export-rs-table "$EXPORT_RS_TABLE"' in run_script
    assert '--export-rs-sslmode "${EXPORT_RS_SSLMODE:-require}"' in run_script
    assert "SNOWFLAKE_PASSWORD secret is required when export_connector=snowflake." in run_script
    assert "REDSHIFT_PASSWORD secret is required when export_connector=redshift." in run_script
    assert (
        "EXPORT_GCS_BUCKET repository variable is required when export_connector=gcs." in run_script
    )
    assert (
        "EXPORT_AZ_ACCOUNT_URL repository variable is required when export_connector=azure_blob."
        in run_script
    )
    assert (
        "EXPORT_AZ_CONTAINER repository variable is required when export_connector=azure_blob."
        in run_script
    )
    assert (
        "EXPORT_RS_HOST repository variable is required when export_connector=redshift."
        in run_script
    )
    assert 'elif [ "$EXPORT_CONNECTOR" = "gcs" ]; then' in run_script
    assert 'elif [ "$EXPORT_CONNECTOR" = "azure_blob" ]; then' in run_script
    assert 'elif [ "$EXPORT_CONNECTOR" = "bigquery" ]; then' in run_script
    assert 'elif [ "$EXPORT_CONNECTOR" = "snowflake" ]; then' in run_script
    assert 'elif [ "$EXPORT_CONNECTOR" = "redshift" ]; then' in run_script
    assert "REDSHIFT_PASSWORD" in call_secrets

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

    benchmark_step = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Generate benchmark summary"
    )
    benchmark_script = str(benchmark_step.get("run", ""))
    assert "llm-diff benchmark artifacts/reports/*.json --format json" in benchmark_script
    assert "artifacts/benchmark/benchmark.json" in benchmark_script
    assert "llm-diff benchmark artifacts/reports/*.json --format markdown" in benchmark_script
    assert "artifacts/benchmark/benchmark.md" in benchmark_script

    benchmark_summary_step = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Append benchmark summary to job summary"
    )
    benchmark_summary_script = str(benchmark_summary_step.get("run", ""))
    assert (
        'cat artifacts/benchmark/benchmark.md >> "$GITHUB_STEP_SUMMARY"' in benchmark_summary_script
    )

    benchmark_upload_step = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Upload benchmark summary"
    )
    assert benchmark_upload_step.get("uses") == (
        "actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f"
    )
    benchmark_upload_with = benchmark_upload_step.get("with")
    assert isinstance(benchmark_upload_with, dict)
    assert benchmark_upload_with.get("path") == "artifacts/benchmark/"
