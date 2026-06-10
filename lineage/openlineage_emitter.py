"""OpenLineage event emitter — generate and validate OpenLineage JSON events."""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_DEAD_LETTER_PATH = Path("./output/dead_letter.json")


def _now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


class OpenLineageEmitter:
    """Generate OpenLineage-compliant JSON events from lineage data.

    Validates each event against a minimal structural schema before export.
    Invalid events are written to a dead letter queue file for manual review.

    Args:
        schema_path: Optional path to an OpenLineage JSON Schema file for
            full validation. Falls back to structural checks if not provided.
    """

    def __init__(self, schema_path: str = "schemas/openlineage.json") -> None:
        self._schema_path = Path(schema_path)
        self._validator = self._load_validator()

    def _load_validator(self) -> Any | None:
        """Load jsonschema validator if available."""
        try:
            import jsonschema

            if self._schema_path.exists():
                with open(self._schema_path, encoding="utf-8") as f:
                    schema = json.load(f)
                return jsonschema.Draft7Validator(schema)
        except ImportError:
            pass
        return None

    def emit(self, lineage_data: dict[str, Any]) -> dict[str, Any]:
        """Convert internal lineage data to an OpenLineage RunEvent.

        Args:
            lineage_data: Internal lineage dict with ``job_name``, ``inputs``,
                ``outputs``, and ``transformations`` keys.

        Returns:
            OpenLineage RunEvent dict.
        """
        run_id = str(uuid.uuid4())
        job_name = lineage_data.get("job_name", "unknown-job")
        namespace = lineage_data.get("namespace", "data-lineage-agent")

        inputs = [self._build_dataset(d) for d in lineage_data.get("inputs", [])]
        outputs = [self._build_dataset(d) for d in lineage_data.get("outputs", [])]

        event: dict[str, Any] = {
            "eventType": "COMPLETE",
            "eventTime": _now_iso(),
            "run": {
                "runId": run_id,
                "facets": {
                    "extractionConfig": {
                        "_producer": "data-lineage-agent",
                        "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/ExtractionConfig.json",
                        "agentVersion": "1.0.0",
                        "language": lineage_data.get("language", "unknown"),
                        "confidence": lineage_data.get("confidence", 0.0),
                    }
                },
            },
            "job": {
                "namespace": namespace,
                "name": job_name,
                "facets": {
                    "sourceCode": {
                        "_producer": "data-lineage-agent",
                        "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/SourceCodeJobFacet.json",
                        "language": lineage_data.get("language", "unknown"),
                        "sourceCode": lineage_data.get("source_snippet", "")[:500],
                    }
                },
            },
            "inputs": inputs,
            "outputs": outputs,
            "producer": "https://github.com/your-org/data-lineage-agent",
            "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json",
        }
        return event

    def emit_from_assertions(
        self,
        assertions: list[dict[str, Any]],
        language: str,
        file_path: str,
    ) -> list[dict[str, Any]]:
        """Generate one OpenLineage event per unique job/program from assertions.

        Args:
            assertions: Verified lineage assertion dicts.
            language: Source language (``"COBOL"``, ``"Java"``, ``"SQL"``).
            file_path: Source file path (used as job name).

        Returns:
            List of OpenLineage RunEvent dicts.
        """
        if not assertions:
            return []

        job_name = Path(file_path).stem
        inputs: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []
        col_lineage: dict[str, list[dict[str, Any]]] = {}

        for assertion in assertions:
            src = assertion.get("source", {})
            tgt = assertion.get("target", {})
            confidence = float(assertion.get("confidence", 0.5))

            if src.get("entity"):
                ds = {
                    "name": src["entity"],
                    "type": src.get("type", "unknown"),
                    "confidence": confidence,
                }
                if ds not in inputs:
                    inputs.append(ds)

            if tgt.get("entity"):
                ds_out = {
                    "name": tgt["entity"],
                    "type": tgt.get("type", "unknown"),
                    "confidence": confidence,
                }
                if ds_out not in outputs:
                    outputs.append(ds_out)

                # Track column lineage
                tgt_col = tgt.get("column", "")
                src_col = src.get("column", "")
                if tgt_col and src_col:
                    if tgt["entity"] not in col_lineage:
                        col_lineage[tgt["entity"]] = []
                    col_lineage[tgt["entity"]].append({
                        "inputField": {
                            "namespace": "file",
                            "dataset": src["entity"],
                            "field": src_col,
                        },
                        "outputField": tgt_col,
                        "transformationType": assertion.get("transformation", {}).get("type", "UNKNOWN"),
                        "transformationDescription": assertion.get("transformation", {}).get("expression", ""),
                    })

        lineage_data = {
            "job_name": job_name,
            "namespace": f"legacy-batch/{language.lower()}",
            "language": language,
            "inputs": inputs,
            "outputs": outputs,
            "confidence": sum(a.get("confidence", 0.5) for a in assertions) / len(assertions),
            "source_snippet": file_path,
        }
        event = self.emit(lineage_data)

        # Attach column lineage facets to outputs
        for output in event.get("outputs", []):
            table_name = output.get("name", "")
            if table_name in col_lineage:
                output.setdefault("facets", {})["columnLineage"] = {
                    "_producer": "data-lineage-agent",
                    "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/ColumnLineageDatasetFacet.json",
                    "fields": {
                        entry["outputField"]: {
                            "inputFields": [entry["inputField"]],
                            "transformationDescription": entry["transformationDescription"],
                            "transformationType": entry["transformationType"],
                        }
                        for entry in col_lineage[table_name]
                    },
                }

        return [event]

    def validate(self, event: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate an event against the OpenLineage schema.

        Args:
            event: OpenLineage RunEvent dict to validate.

        Returns:
            Tuple of ``(is_valid, list_of_error_strings)``.
        """
        errors: list[str] = []

        # Structural checks (always applied)
        required_top = {"eventType", "eventTime", "run", "job", "producer", "schemaURL"}
        for field in required_top:
            if field not in event:
                errors.append(f"Missing required field: {field}")

        if "run" in event and "runId" not in event["run"]:
            errors.append("run.runId is required")
        if "job" in event:
            if "namespace" not in event["job"]:
                errors.append("job.namespace is required")
            if "name" not in event["job"]:
                errors.append("job.name is required")

        # JSON Schema validation (if available)
        if self._validator and not errors:
            for error in self._validator.iter_errors(event):
                errors.append(error.message)

        return len(errors) == 0, errors

    def to_file(self, events: list[dict[str, Any]], output_path: str) -> None:
        """Write validated events to a JSON file; invalid ones to dead letter queue.

        Args:
            events: List of OpenLineage RunEvent dicts.
            output_path: File path to write valid events to.
        """
        valid: list[dict[str, Any]] = []
        dead_letter: list[dict[str, Any]] = []

        for event in events:
            is_valid, errs = self.validate(event)
            if is_valid:
                valid.append(event)
            else:
                dead_letter.append({"event": event, "errors": errs})

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(valid, indent=2), encoding="utf-8")
        print(f"[openlineage] Written {len(valid)} valid events to {output_path}")

        if dead_letter:
            _DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)
            existing: list[dict] = []
            if _DEAD_LETTER_PATH.exists():
                try:
                    existing = json.loads(_DEAD_LETTER_PATH.read_text())
                except Exception:
                    existing = []
            existing.extend(dead_letter)
            _DEAD_LETTER_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            print(f"[openlineage] {len(dead_letter)} invalid events → dead letter: {_DEAD_LETTER_PATH}")

    @staticmethod
    def _build_dataset(data: dict[str, Any]) -> dict[str, Any]:
        """Build an OpenLineage Dataset object from internal format.

        Args:
            data: Internal dataset dict with ``name``, ``type`` keys.

        Returns:
            OpenLineage Dataset dict.
        """
        name = data.get("name", "unknown")
        ds_type = data.get("type", "unknown")
        namespace = "file://" if "file" in ds_type.lower() else "db://"
        return {
            "namespace": namespace,
            "name": name,
            "facets": {
                "schema": {
                    "_producer": "data-lineage-agent",
                    "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/SchemaDatasetFacet.json",
                    "fields": data.get("columns", []),
                },
                "dataSource": {
                    "_producer": "data-lineage-agent",
                    "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/DatasourceDatasetFacet.json",
                    "name": name,
                    "uri": f"{namespace}{name}",
                },
            },
        }
