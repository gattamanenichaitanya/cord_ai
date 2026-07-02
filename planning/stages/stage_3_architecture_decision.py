import json
import sys
from pathlib import Path
from typing import Dict, Any, List

from planning.claude_client import ClaudeClient
from planning.models import ExtractedRequirement, Stage2Output, ArchitectureDecision


class StageOutputWarning(Exception):
    """Raised when stage output fails architectural validation rules."""
    pass


def run_stage_3(
    requirement: ExtractedRequirement,
    stage_2_output: Stage2Output,
    client: ClaudeClient,
    run_dir: Path,
    graph_root: Path = Path("graph/hubspot")
) -> ArchitectureDecision:
    project_root = Path(__file__).resolve().parent.parent.parent
    prompt_path = project_root / "planning" / "prompts" / "stage_3_architecture_decision.txt"

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    # 1. Load full JSON content for high-confidence candidates (relevance_score >= 0.7)
    full_entries: List[Dict[str, Any]] = []
    for candidate in stage_2_output.candidates:
        if candidate.relevance_score >= 0.7:
            file_path = project_root / candidate.file_path
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        entry_json = json.load(f)
                        full_entries.append({
                            "entry_id": candidate.entry_id,
                            "entry_type": candidate.entry_type,
                            "file_path": candidate.file_path,
                            "relevance_score": candidate.relevance_score,
                            "content": entry_json
                        })
                except Exception as e:
                    print(f"[Warning] Failed to read graph entry at {file_path}: {e}")

    # 2. Build prompt
    req_json_str = requirement.model_dump_json(indent=2)
    s2_json_str = stage_2_output.model_dump_json(indent=2)
    full_entries_str = json.dumps(full_entries, indent=2)

    composed_prompt = (
        prompt_template.replace("{{requirement}}", req_json_str)
        .replace("{{stage_2_output}}", s2_json_str)
        .replace("{{full_graph_entries}}", full_entries_str)
    )

    # 3. Call Claude
    output, metadata = client.call_with_structured_output(
        prompt=composed_prompt,
        output_model=ArchitectureDecision,
        max_tokens=4096
    )

    # Ensure requirement_id matches
    output.requirement_id = requirement.id

    # 4. Validation
    if not output.selected_capabilities:
        raise StageOutputWarning(f"Stage 3 [{requirement.id}]: Architecture decision selected 0 capabilities.")
    if not output.selected_operations:
        raise StageOutputWarning(f"Stage 3 [{requirement.id}]: Architecture decision selected 0 operations.")
    if not output.parameters:
        raise StageOutputWarning(f"Stage 3 [{requirement.id}]: Architecture decision parameters dictionary is empty.")

    # 5. Persist
    run_dir.mkdir(parents=True, exist_ok=True)
    out_file = run_dir / f"stage_3_{requirement.id}_output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output.model_dump_json(indent=2))

    # 6. Print summary
    print(f"Stage 3 [{requirement.id}]: Selected approach '{output.chosen_approach}'. Ops: {output.selected_operations}")

    return output


if __name__ == "__main__":
    from planning.document_loader import load_document
    from planning.stages.stage_1_extraction import run_stage_1
    from planning.stages.stage_2_concept_mapping import run_stage_2

    doc_path = sys.argv[1] if len(sys.argv) > 1 else "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    target_req_id = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Loading document: {doc_path}...")
    doc = load_document(doc_path)
    client = ClaudeClient()
    run_dir = Path("runs/cli_test_stage_3")

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

    # Select target requirement
    target_req = None
    if target_req_id:
        for r in s1_output.requirements:
            if r.id == target_req_id:
                target_req = r
                break
    if not target_req:
        for r in s1_output.requirements:
            if r.requirement_type.value == "workflow":
                target_req = r
                break
        if not target_req:
            target_req = s1_output.requirements[0]

    # Load or run Stage 2
    s2_file = run_dir / f"stage_2_{target_req.id}_output.json"
    if s2_file.exists():
        print(f"Loading cached Stage 2 output from {s2_file}...")
        with open(s2_file, "r", encoding="utf-8") as f:
            s2_output = Stage2Output.model_validate_json(f.read())
    else:
        print(f"Running Stage 2 Concept Mapping for {target_req.id}...")
        s2_output = run_stage_2(target_req, client, run_dir)

    print(f"\nRunning Stage 3 Architecture Decision for requirement: {target_req.id} - '{target_req.title}'...")
    s3_output = run_stage_3(target_req, s2_output, client, run_dir)

    print("\n" + "="*80)
    print(f"STAGE 3 ARCHITECTURE DECISION RESULTS ({target_req.id})")
    print("="*80)
    print(f"Chosen Approach: {s3_output.chosen_approach}\n")
    print(f"Rationale: {s3_output.rationale}\n")
    print(f"Selected Capabilities: {s3_output.selected_capabilities}")
    print(f"Selected Operations: {s3_output.selected_operations}\n")
    print("Parameters:")
    print(json.dumps(s3_output.parameters, indent=2))
    if s3_output.rejected_alternatives:
        print("\nRejected Alternatives:")
        for rej in s3_output.rejected_alternatives:
            print(f"  - Alternative: {rej.get('alternative')}")
            print(f"    Reason: {rej.get('reason')}")
    print("="*80)
