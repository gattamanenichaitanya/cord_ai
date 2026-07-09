import json
import sys
from pathlib import Path
from typing import Dict, Any, List

from planning.claude_client import ClaudeClient
from planning.models import ExtractedRequirement, ArchitectureDecision, Stage4Output, Stage5Output


def run_stage_5(
    requirement: ExtractedRequirement,
    architecture_decision: ArchitectureDecision,
    stage_4_output: Stage4Output,
    client: ClaudeClient,
    run_dir: Path,
    graph_root: Path = Path("graph/hubspot")
) -> Stage5Output:
    project_root = Path(__file__).resolve().parent.parent.parent
    prompt_path = project_root / "planning" / "prompts" / "stage_5_gap_detection.txt"

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    # Load all gotchas from graph_root / gotchas
    gotchas_dir = project_root / graph_root / "gotchas"
    gotchas_context: List[Dict[str, Any]] = []
    if gotchas_dir.exists():
        for file in gotchas_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    gotcha_data = json.load(f)
                    gotchas_context.append({
                        "file_name": file.name,
                        "content": gotcha_data
                    })
            except Exception as e:
                print(f"[Warning] Failed to load gotcha file {file.name}: {e}")

    # Build prompt
    req_str = requirement.model_dump_json(indent=2)
    arch_str = architecture_decision.model_dump_json(indent=2)
    s4_str = stage_4_output.model_dump_json(indent=2)
    gotchas_str = json.dumps(gotchas_context, indent=2)

    composed_prompt = (
        prompt_template.replace("{{requirement}}", req_str)
        .replace("{{architecture_decision}}", arch_str)
        .replace("{{stage_4_output}}", s4_str)
        .replace("{{gotchas_context}}", gotchas_str)
    )

    # Call Claude
    output, metadata = client.call_with_structured_output(
        prompt=composed_prompt,
        output_model=Stage5Output,
        max_tokens=4096
    )

    # Ensure requirement_id matches
    output.requirement_id = requirement.id

    # Persist
    run_dir.mkdir(parents=True, exist_ok=True)
    out_file = run_dir / f"stage_5_{requirement.id}_output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output.model_dump_json(indent=2))

    print(f"Stage 5 [{requirement.id}]: {output.summary}")
    return output


if __name__ == "__main__":
    from planning.document_loader import load_document
    from planning.stages.stage_1_extraction import run_stage_1
    from planning.stages.stage_2_concept_mapping import run_stage_2
    from planning.stages.stage_3_architecture_decision import run_stage_3
    from planning.stages.stage_4_state_inspection import run_stage_4

    doc_path = sys.argv[1] if len(sys.argv) > 1 else "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    target_req_id = sys.argv[2] if len(sys.argv) > 2 else "REQ-009"

    print(f"Loading document: {doc_path}...")
    doc = load_document(doc_path)
    client = ClaudeClient()
    run_dir = Path("runs/cli_test_stage_5")

    # Load or run Stage 1
    s1_file = run_dir / "stage_1_output.json"
    if s1_file.exists():
        print(f"Loading cached Stage 1 output from {s1_file}...")
        from planning.models import Stage1Output
        with open(s1_file, "r", encoding="utf-8") as f:
            s1_output = Stage1Output.model_validate_json(f.read())
    else:
        print("Running Stage 1 Extraction...")
        s1_output = run_stage_1(doc, client, run_dir)

    target_req = None
    for r in s1_output.requirements:
        if r.id == target_req_id:
            target_req = r
            break
    if not target_req:
        target_req = s1_output.requirements[0]

    # Load or run Stage 2
    s2_file = run_dir / f"stage_2_{target_req.id}_output.json"
    if s2_file.exists():
        print(f"Loading cached Stage 2 output from {s2_file}...")
        from planning.models import Stage2Output
        with open(s2_file, "r", encoding="utf-8") as f:
            s2_output = Stage2Output.model_validate_json(f.read())
    else:
        print(f"Running Stage 2 Concept Mapping for {target_req.id}...")
        s2_output = run_stage_2(target_req, client, run_dir)

    # Load or run Stage 3
    s3_file = run_dir / f"stage_3_{target_req.id}_output.json"
    if s3_file.exists():
        print(f"Loading cached Stage 3 output from {s3_file}...")
        from planning.models import ArchitectureDecision
        with open(s3_file, "r", encoding="utf-8") as f:
            s3_output = ArchitectureDecision.model_validate_json(f.read())
    else:
        print(f"Running Stage 3 Architecture Decision for {target_req.id}...")
        s3_output = run_stage_3(target_req, s2_output, client, run_dir)

    # Load or run Stage 4
    s4_file = run_dir / f"stage_4_{target_req.id}_output.json"
    if s4_file.exists():
        print(f"Loading cached Stage 4 output from {s4_file}...")
        from planning.models import Stage4Output
        with open(s4_file, "r", encoding="utf-8") as f:
            s4_output = Stage4Output.model_validate_json(f.read())
    else:
        print(f"Running Stage 4 Live State Inspection for {target_req.id}...")
        s4_output = run_stage_4(target_req, s3_output, run_dir)

    print(f"\nRunning Stage 5 Gap Detection for requirement: {target_req.id} - '{target_req.title}'...")
    s5_output = run_stage_5(target_req, s3_output, s4_output, client, run_dir)

    print("\n" + "="*80)
    print(f"STAGE 5 GAP DETECTION RESULTS ({target_req.id})")
    print("="*80)
    print(f"Summary: {s5_output.summary}\n")
    print("Detected Gaps:")
    for gap in s5_output.gaps:
        print(f"  - [{gap.severity.value.upper()}] {gap.title} (Blocks: {gap.blocks_execution})")
        if gap.referenced_gotcha:
            print(f"    Referenced Gotcha: {gap.referenced_gotcha}")
        print(f"    Description: {gap.description}")
        print(f"    Suggested Resolution: {gap.suggested_resolution}")
        print("-" * 60)
    print("="*80)
