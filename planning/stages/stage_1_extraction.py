import json
import sys
from pathlib import Path
from typing import Counter

from planning.claude_client import ClaudeClient
from planning.document_loader import DocumentInput, load_document
from planning.models import Stage1Output, ExtractedRequirement


class StageOutputWarning(Exception):
    """Raised when stage output validates syntactically but fails logical validation."""
    pass


def run_stage_1(
    document: DocumentInput,
    client: ClaudeClient,
    run_dir: Path
) -> Stage1Output:
    project_root = Path(__file__).resolve().parent.parent.parent
    prompt_path = project_root / "planning" / "prompts" / "stage_1_extraction.txt"
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    composed_prompt = prompt_template.replace("{{document_content}}", document.content_markdown)

    output, metadata = client.call_with_structured_output(
        prompt=composed_prompt,
        output_model=Stage1Output,
        max_tokens=8192
    )

    # Validation checks
    if not output.requirements:
        raise StageOutputWarning("Stage 1 output contained zero extracted requirements.")

    req_ids = [r.id for r in output.requirements]
    if len(req_ids) != len(set(req_ids)):
        raise StageOutputWarning("Duplicate requirement IDs detected in Stage 1 output.")

    valid_id_set = set(req_ids)
    for req in output.requirements:
        for dep in req.dependencies:
            if dep not in valid_id_set:
                print(f"[Warning] Requirement {req.id} references non-existent dependency ID {dep}.")

    # Save output to run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    out_file = run_dir / "stage_1_output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output.model_dump_json(indent=2))

    # Summary reporting
    type_counts = dict(Counter(r.requirement_type.value for r in output.requirements))
    cost_info = client.get_cost_summary()
    cost_str = f"${cost_info['estimated_cost_usd']:.4f}"

    print(f"\nStage 1: Extracted {len(output.requirements)} requirements across {document.section_count} sections. Types: {type_counts}. Cost: {cost_str}")
    return output


if __name__ == "__main__":
    doc_path = sys.argv[1] if len(sys.argv) > 1 else "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    print(f"Loading document: {doc_path}...")
    doc = load_document(doc_path)
    
    client = ClaudeClient()
    run_dir = Path("runs/cli_test_stage_1")
    
    print("Running Stage 1 Extraction...")
    result = run_stage_1(doc, client, run_dir)
    
    print("\n" + "="*80)
    print(f"STAGE 1 EXTRACTION RESULTS ({len(result.requirements)} REQUIREMENTS)")
    print("="*80)
    for req in result.requirements:
        deps_str = f" (Depends on: {', '.join(req.dependencies)})" if req.dependencies else ""
        print(f"[{req.id}] {req.title} ({req.requirement_type.value}){deps_str}")
        print(f"  Section: {req.source_section}")
        print(f"  Description: {req.description}")
        print(f"  Excerpt: {req.source_excerpt[:100]}...")
        print("-" * 80)
