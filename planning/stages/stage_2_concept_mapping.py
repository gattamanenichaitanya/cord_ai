import json
import sys
from pathlib import Path
from typing import Dict, Any, List

from graph_db.search import search_graph
from planning.claude_client import ClaudeClient
from planning.models import ExtractedRequirement, Stage2Output


def run_stage_2(
    requirement: ExtractedRequirement,
    client: ClaudeClient,
    run_dir: Path
) -> Stage2Output:
    project_root = Path(__file__).resolve().parent.parent.parent
    prompt_path = project_root / "planning" / "prompts" / "stage_2_concept_mapping.txt"

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    # 1. Build search queries
    queries = [requirement.title, requirement.description]
    if requirement.source_excerpt and requirement.source_excerpt != requirement.description:
        queries.append(requirement.source_excerpt)

    # 2. Run search_graph and 3. Deduplicate
    candidate_map: Dict[str, Dict[str, Any]] = {}
    for q in queries:
        results = search_graph(q, n_results=10)
        for r in results:
            entry_id = r["metadata"]["entry_id"]
            dist = r["distance"]
            if entry_id not in candidate_map or dist < candidate_map[entry_id]["distance"]:
                candidate_map[entry_id] = {
                    "entry_id": entry_id,
                    "entry_type": r["metadata"]["type"],
                    "file_path": r["file_path"],
                    "distance": dist,
                    "text_preview": r["text"][:300].replace("\n", " ")
                }

    sorted_candidates = sorted(candidate_map.values(), key=lambda x: x["distance"])[:15]

    # 4. Compose prompt
    req_json_str = requirement.model_dump_json(indent=2)
    candidates_json_str = json.dumps(sorted_candidates, indent=2)

    composed_prompt = prompt_template.replace("{{requirement}}", req_json_str).replace("{{candidates_list}}", candidates_json_str)

    # 5. Call Claude
    output, metadata = client.call_with_structured_output(
        prompt=composed_prompt,
        output_model=Stage2Output
    )

    # Ensure requirement_id matches
    output.requirement_id = requirement.id

    # 6. Persist to disk
    run_dir.mkdir(parents=True, exist_ok=True)
    out_file = run_dir / f"stage_2_{requirement.id}_output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output.model_dump_json(indent=2))

    # 7. Print summary
    selected_count = len(output.candidates)
    print(f"Stage 2 [{requirement.id}]: Considered {len(sorted_candidates)} candidates, selected {selected_count} with confidence >= 0.5")

    return output


if __name__ == "__main__":
    from planning.document_loader import load_document
    from planning.stages.stage_1_extraction import run_stage_1

    doc_path = sys.argv[1] if len(sys.argv) > 1 else "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    target_req_id = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Loading document: {doc_path}...")
    doc = load_document(doc_path)
    client = ClaudeClient()
    run_dir = Path("runs/cli_test_stage_2")

    # Run or load Stage 1
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
        # Default to REQ-009 or the first workflow requirement
        for r in s1_output.requirements:
            if r.requirement_type.value == "workflow":
                target_req = r
                break
        if not target_req:
            target_req = s1_output.requirements[0]

    print(f"\nRunning Stage 2 Concept Mapping for requirement: {target_req.id} - '{target_req.title}'...")
    s2_output = run_stage_2(target_req, client, run_dir)

    print("\n" + "="*80)
    print(f"STAGE 2 CONCEPT MAPPING RESULTS ({target_req.id})")
    print("="*80)
    print(f"Interpretation: {s2_output.interpretation}\n")
    print("Mapped Candidates (Confidence >= 0.5):")
    for c in s2_output.candidates:
        print(f"  - [{c.relevance_score:.2f}] {c.entry_id} ({c.entry_type})")
        print(f"    Path: {c.file_path}")
        print(f"    Reasoning: {c.reasoning}")
    
    if s2_output.ambiguities:
        print("\nIdentified Ambiguities:")
        for amb in s2_output.ambiguities:
            print(f"  - {amb}")
    print("="*80)
