from datetime import datetime
from pathlib import Path
import pytest
from planning.claude_client import ClaudeClient
from planning.document_loader import load_document
from planning.stages.stage_1_extraction import run_stage_1
from planning.stages.stage_2_concept_mapping import run_stage_2
from planning.stages.stage_3_architecture_decision import run_stage_3
from planning.stages.stage_4_state_inspection import run_stage_4
from planning.stages.stage_5_gap_detection import run_stage_5
from planning.stages.stage_6_plan_finalization import run_stage_6
from planning.models import ImplementationPlan

@pytest.fixture(scope="module")
def stage_6_results(tmp_path_factory):
    progress_log = Path("runs/stage_progress.log")
    progress_log.parent.mkdir(parents=True, exist_ok=True)

    def log_progress(msg):
        print(f"[TEST PROGRESS] {msg}", flush=True)
        with open(progress_log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")

    # Clear log at start
    with open(progress_log, "w", encoding="utf-8") as f:
        f.write("")

    doc_path = "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    log_progress(f"Loading document: {doc_path}")
    doc = load_document(doc_path)
    client = ClaudeClient()
    run_dir = tmp_path_factory.mktemp("stage_6_test_run")
    
    log_progress("Running Stage 1 Extraction...")
    s1 = run_stage_1(doc, client, run_dir)
    target_req = s1.requirements[0] # Test with first extracted requirement
    
    # Default to REQ-009 if present
    for r in s1.requirements:
        if r.id == "REQ-009":
            target_req = r
            break
            
    log_progress(f"Target requirement selected: {target_req.id} - '{target_req.title}'")

    log_progress("Running Stage 2 Concept Mapping...")
    s2 = run_stage_2(target_req, client, run_dir)

    log_progress("Running Stage 3 Architecture Decision...")
    s3 = run_stage_3(target_req, s2, client, run_dir)

    log_progress("Running Stage 4 Live State Inspection...")
    s4 = run_stage_4(target_req, s3, run_dir)

    log_progress("Running Stage 5 Gap Detection...")
    s5 = run_stage_5(target_req, s3, s4, client, run_dir)
    
    log_progress("Running Stage 6 Plan Finalization...")
    pipeline_metadata = {
        "document_title": doc.title,
        "loaded_at": doc.loaded_at.isoformat()
    }
    
    output = run_stage_6(
        requirement=target_req,
        architecture_decision=s3,
        stage_5_output=s5,
        client=client,
        run_dir=run_dir,
        document_path=str(Path(doc_path)),
        pipeline_metadata=pipeline_metadata
    )
    log_progress("Stage 6 execution complete!")
    return output, run_dir, target_req

@pytest.mark.integration
def test_stage_6_returns_implementation_plan(stage_6_results):
    output, _, _ = stage_6_results
    assert isinstance(output, ImplementationPlan)
    assert len(output.actions) >= 1
    assert output.chosen_approach != ""
    assert output.rationale != ""
    assert "execution_order_rationale" in output.pipeline_metadata

@pytest.mark.integration
def test_stage_6_persists_to_disk(stage_6_results):
    _, run_dir, _ = stage_6_results
    output_file = run_dir / "stage_6_final_plan.json"
    assert output_file.exists()
    assert output_file.stat().st_size > 0
