"""Unit tests for column_lineage_extraction_node."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from models.lineage_models import ColumnLineageRecord
from src.models import AgentState, AnalysisResult


@pytest.fixture
def sample_state(tmp_path: Path) -> AgentState:
    """Build a sample agent state with one COBOL file."""
    cobol_file = tmp_path / "CUSTPROG.cbl"
    cobol_file.write_text(
        "MOVE WS-CUST-ID TO OUT-CUST-ID.\nMOVE WS-BALANCE TO OUT-BALANCE."
    )
    result = AnalysisResult(
        file_path=str(cobol_file),
        language="cobol",
        reads_from=["CUSTOMER_FILE"],
        writes_to=["OUTPUT_FILE"],
        confidence=0.9,
    )
    return {
        "repo_path": str(tmp_path),
        "analysis_results": {str(cobol_file): result},
        "file_manifest": [],
        "config_map": {},
        "jcl_dd_map": {},
        "lineage_nodes": [],
        "lineage_edges": [],
        "unresolved_refs": [],
        "errors": [],
        "output_json_path": "",
        "column_lineage_records": [],
    }


def test_column_lineage_node_returns_records(sample_state: AgentState) -> None:
    """column_lineage_extraction_node should return column records in state."""
    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="""[
        {
            "source_column": "WS-CUST-ID",
            "transformation_name": "MOVE-CUST-ID",
            "transformation_type": "MOVE",
            "transformation_code_snippet": "MOVE WS-CUST-ID TO OUT-CUST-ID.",
            "target_column": "OUT-CUST-ID",
            "confidence_score": 0.9
        }
    ]""")

    with patch("nodes.column_lineage_node._make_nova_lite_llm", return_value=mock_llm):
        from nodes.column_lineage_node import column_lineage_extraction_node

        result = column_lineage_extraction_node(sample_state)

    assert "column_lineage_records" in result
    records = result["column_lineage_records"]
    assert len(records) >= 1
    assert isinstance(records[0], ColumnLineageRecord)
    assert records[0].source_column == "WS-CUST-ID"
    assert records[0].target_column == "OUT-CUST-ID"


def test_column_lineage_node_skips_non_cobol_java(sample_state: AgentState) -> None:
    """Node should skip JCL and config files."""
    jcl_result = AnalysisResult(
        file_path="SOMEJOB.jcl",
        language="jcl",
        reads_from=["INPUT"],
        writes_to=["OUTPUT"],
        confidence=0.8,
    )
    sample_state["analysis_results"] = {"SOMEJOB.jcl": jcl_result}

    with patch("nodes.column_lineage_node._make_nova_lite_llm") as mock_llm_factory:
        from nodes.column_lineage_node import column_lineage_extraction_node

        result = column_lineage_extraction_node(sample_state)

    mock_llm_factory.assert_not_called()
    assert result["column_lineage_records"] == []


def test_column_lineage_node_empty_analysis(sample_state: AgentState) -> None:
    """Node should handle empty analysis_results gracefully."""
    sample_state["analysis_results"] = {}
    from nodes.column_lineage_node import column_lineage_extraction_node

    result = column_lineage_extraction_node(sample_state)
    assert result["column_lineage_records"] == []


def test_column_lineage_record_low_confidence_flag() -> None:
    """ColumnLineageRecord.low_confidence should be True when confidence < 0.6."""
    rec = ColumnLineageRecord(
        source_file="f.cbl",
        source_column="A",
        transformation_name="T",
        transformation_type="MOVE",
        transformation_code_snippet="MOVE A TO B.",
        target_file="g.cbl",
        target_column="B",
        confidence_score=0.4,
    )
    assert rec.low_confidence is True


def test_column_lineage_record_high_confidence_flag() -> None:
    """ColumnLineageRecord.low_confidence should be False when confidence >= 0.6."""
    rec = ColumnLineageRecord(
        source_file="f.cbl",
        source_column="A",
        transformation_name="T",
        transformation_type="MOVE",
        transformation_code_snippet="MOVE A TO B.",
        target_file="g.cbl",
        target_column="B",
        confidence_score=0.8,
    )
    assert rec.low_confidence is False
