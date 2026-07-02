from pathlib import Path
import pytest
from planning.claude_client import ClaudeClient
from planning.document_loader import load_document
from planning.stages.stage_1_extraction import run_stage_1

@pytest.fixture(scope="module")
def stage_1_results(tmp_path_factory):
    doc_path = "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    doc = load_document(doc_path)
    client = ClaudeClient()
    run_dir = tmp_path_factory.mktemp("stage_1_test_run")
    output = run_stage_1(doc, client, run_dir)
    return output, run_dir

@pytest.mark.integration
def test_stage_1_returns_multiple_requirements(stage_1_results):
    output, _ = stage_1_results
    assert len(output.requirements) > 3

@pytest.mark.integration
def test_stage_1_finds_at_risk_workflow(stage_1_results):
    output, _ = stage_1_results
    matching = [
        r for r in output.requirements
        if r.requirement_type.value == "workflow"
        and "6.1" in r.source_section
        and ("risk" in r.description.lower() or "at-risk" in r.description.lower())
    ]
    assert len(matching) >= 1

@pytest.mark.integration
def test_stage_1_dependencies_are_valid(stage_1_results):
    output, _ = stage_1_results
    valid_ids = {r.id for r in output.requirements}
    for r in output.requirements:
        for dep in r.dependencies:
            assert dep in valid_ids, f"Dependency ID {dep} in {r.id} not found in valid IDs {valid_ids}"

@pytest.mark.integration
def test_stage_1_unique_ids(stage_1_results):
    output, _ = stage_1_results
    ids = [r.id for r in output.requirements]
    assert len(ids) == len(set(ids))

@pytest.mark.integration
def test_stage_1_persists_to_disk(stage_1_results):
    _, run_dir = stage_1_results
    output_file = run_dir / "stage_1_output.json"
    assert output_file.exists()
    assert output_file.stat().st_size > 0
