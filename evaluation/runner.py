"""Three-level evaluation framework for lineage extraction quality."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.golden_dataset_generator import GoldenDatasetGenerator
from evaluation.level1_assertion import AssertionEvaluator
from evaluation.level2_file import FileEvaluator
from evaluation.level3_system import SystemEvaluator
from parsers.orchestrator import ParserOrchestrator


class EvaluationRunner:
    """Orchestrate evaluation workflows and emit JSON reports."""

    def __init__(
        self,
        golden_generator: GoldenDatasetGenerator | None = None,
        orchestrator: ParserOrchestrator | None = None,
    ) -> None:
        self._golden_gen = golden_generator or GoldenDatasetGenerator()
        self._orchestrator = orchestrator or ParserOrchestrator()
        self._level1 = AssertionEvaluator()
        self._level2 = FileEvaluator()
        self._level3 = SystemEvaluator()

    def run_full_evaluation(
        self,
        extracted_dir: str,
        golden_dir: str,
    ) -> dict[str, Any]:
        """Run file-level and system-level evaluation from saved JSON assets.

        Args:
            extracted_dir: Directory containing extracted lineage JSON files.
            golden_dir: Directory containing generated ``*.golden.json`` files.

        Returns:
            Complete evaluation report.
        """
        golden_map: dict[str, dict[str, Any]] = {}
        golden_cross_language: list[dict[str, Any]] = []
        for golden_file in Path(golden_dir).glob('*.golden.json'):
            golden = json.loads(golden_file.read_text(encoding='utf-8'))
            golden_map[Path(golden.get('file_path', golden_file.name)).stem] = golden
            golden_cross_language.extend(golden.get('ground_truth_cross_language', []))

        extracted_map: dict[str, list[dict[str, Any]]] = {}
        for extracted_file in Path(extracted_dir).glob('*_lineage.json'):
            stem = extracted_file.stem.replace('_lineage', '')
            try:
                events = json.loads(extracted_file.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            extracted_map[stem] = self._flatten_events(events)

        file_results: list[dict[str, Any]] = []
        for stem, golden in golden_map.items():
            extracted = extracted_map.get(stem, [])
            result = self._level2.evaluate(extracted, golden)
            result['openlineage_events'] = self._normalise_events(extracted)
            file_results.append(result)

        system_result = self._level3.evaluate(file_results, golden_cross_language)
        report = {
            'evaluation_timestamp': datetime.now(UTC).isoformat(),
            'summary': system_result,
            'file_results': file_results,
        }
        self._save_report(report)
        self._print_summary(report)
        return report

    def _flatten_events(self, events: Any) -> list[dict[str, Any]]:
        """Convert OpenLineage-style events to assertion-like structures."""
        if not isinstance(events, list):
            return []
        assertions: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            for input_dataset in event.get('inputs', []):
                for output_dataset in event.get('outputs', []):
                    assertions.append(
                        {
                            'source': {
                                'entity': input_dataset.get('name', ''),
                                'column': '',
                                'type': 'table',
                            },
                            'target': {
                                'entity': output_dataset.get('name', ''),
                                'column': '',
                                'type': 'table',
                            },
                            'transformation': {
                                'type': event.get('eventType', 'EXTRACTED'),
                                'expression': event.get('job', {}).get('name', ''),
                                'line': 0,
                            },
                            'confidence': output_dataset.get('confidence', 0.5),
                        }
                    )
        return assertions

    def _normalise_events(self, assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Wrap assertion-like records in a minimal OpenLineage event shape."""
        events: list[dict[str, Any]] = []
        for assertion in assertions:
            events.append(
                {
                    'eventType': assertion.get('transformation', {}).get('type', 'COMPLETE'),
                    'eventTime': datetime.now(UTC).isoformat(),
                    'job': {'namespace': 'evaluation', 'name': 'flattened_assertion'},
                    'inputs': [{'name': assertion.get('source', {}).get('entity', '')}],
                    'outputs': [{'name': assertion.get('target', {}).get('entity', '')}],
                }
            )
        return events

    def _save_report(self, report: dict[str, Any]) -> None:
        """Persist the evaluation report under ``evaluation/reports``."""
        reports_dir = Path('evaluation/reports')
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
        report_path = reports_dir / f'eval_{timestamp}.json'
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'[eval] Report saved to {report_path}')

    @staticmethod
    def _print_summary(report: dict[str, Any]) -> None:
        """Print a concise summary to stdout."""
        summary = report['summary']
        print('\n' + '=' * 60)
        print('EVALUATION SUMMARY')
        print('=' * 60)
        for key, value in summary.items():
            print(f'  {key:<35} {value}')
        print('=' * 60 + '\n')


__all__ = [
    'GoldenDatasetGenerator',
    'AssertionEvaluator',
    'FileEvaluator',
    'SystemEvaluator',
    'EvaluationRunner',
]
