from datetime import datetime
from uuid import uuid4
from pathlib import Path
from pydantic import BaseModel
from planning.models import PlanAction, ImplementationPlan


def run_stage_6(
    requirement,
    architecture_decision,
    stage_5_output,
    client,
    run_dir: Path,
    document_path: str,
    pipeline_metadata: dict
) -> ImplementationPlan:
    """
    Combined dependency resolution + plan synthesis.
    Replaces the previous Stage 6 and Stage 7.
    """
    
    # Load the prompt template
    prompt_template = Path("planning/prompts/stage_6_plan_finalization.txt").read_text()
    
    prompt = prompt_template.replace(
        "{{requirement}}", requirement.model_dump_json(indent=2)
    ).replace(
        "{{architecture_decision}}", architecture_decision.model_dump_json(indent=2)
    ).replace(
        "{{stage_5_gaps}}", stage_5_output.model_dump_json(indent=2)
    )
    
    # Ask Claude for actions + polished text in one call
    class Stage6PartialOutput(BaseModel):
        actions: list[PlanAction]
        polished_approach: str
        polished_rationale: str
        execution_order_rationale: str
    
    partial, metadata = client.call_with_structured_output(
        prompt=prompt,
        output_model=Stage6PartialOutput,
        max_tokens=4096
    )
    
    # Validate dependency references
    action_ids = {a.action_id for a in partial.actions}
    for action in partial.actions:
        for dep in action.depends_on:
            if dep not in action_ids:
                raise ValueError(f"Action {action.action_id} depends on invalid id {dep}")
    
    # Assemble the final plan
    plan = ImplementationPlan(
        plan_id=f"{requirement.id}-{datetime.now().strftime('%Y%m%dT%H%M%S')}",
        requirement_id=requirement.id,
        requirement_title=requirement.title,
        document_source=document_path,
        actions=partial.actions,
        chosen_approach=partial.polished_approach,
        rationale=partial.polished_rationale,
        identified_gaps=stage_5_output.gaps,
        created_at=datetime.now(),
        pipeline_metadata={
            **pipeline_metadata,
            "stage_6_tokens": metadata.get("input_tokens", 0) + metadata.get("output_tokens", 0),
            "execution_order_rationale": partial.execution_order_rationale
        },
        approved=False,
        approval_notes=None
    )
    
    # Persist
    plan_path = run_dir / "stage_6_final_plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    
    print(f"Stage 6 [Plan Finalization]: {len(plan.actions)} actions ordered, "
          f"{len(plan.identified_gaps)} gaps carried forward. "
          f"Cost: ${metadata.get('cost', 0):.3f}")
    
    return plan


if __name__ == "__main__":
    import sys
    from planning.claude_client import ClaudeClient
    from planning.models import Stage1Output, ArchitectureDecision, Stage5Output

    doc_path = sys.argv[1] if len(sys.argv) > 1 else "test_documents/Acme-Corp-HubSpot-System-Design-Document-v2.1.docx"
    target_req_id = sys.argv[2] if len(sys.argv) > 2 else "REQ-009"

    client = ClaudeClient()
    run_dir = Path("runs/cli_test_stage_5")

    print(f"Loading outputs from {run_dir} for requirement {target_req_id}...")

    # Load Stage 1 to find the requirement
    s1_file = run_dir / "stage_1_output.json"
    if not s1_file.exists():
        print(f"Error: {s1_file} does not exist. Please run Stage 1 first.")
        sys.exit(1)
        
    with open(s1_file, "r", encoding="utf-8") as f:
        s1_output = Stage1Output.model_validate_json(f.read())

    target_req = None
    for r in s1_output.requirements:
        if r.id == target_req_id:
            target_req = r
            break
            
    if not target_req:
        print(f"Error: Requirement {target_req_id} not found in Stage 1 output.")
        sys.exit(1)

    # Load Stage 3 Architecture Decision
    s3_file = run_dir / f"stage_3_{target_req_id}_output.json"
    if not s3_file.exists():
        print(f"Error: {s3_file} does not exist. Please run Stage 3 first.")
        sys.exit(1)
        
    with open(s3_file, "r", encoding="utf-8") as f:
        s3_output = ArchitectureDecision.model_validate_json(f.read())

    # Load Stage 5 Gap Detection
    s5_file = run_dir / f"stage_5_{target_req_id}_output.json"
    if not s5_file.exists():
        print(f"Error: {s5_file} does not exist. Please run Stage 5 first.")
        sys.exit(1)
        
    with open(s5_file, "r", encoding="utf-8") as f:
        s5_output = Stage5Output.model_validate_json(f.read())

    pipeline_metadata = {
        "document_title": s1_output.document_summary[:100],
        "loaded_at": datetime.now().isoformat()
    }

    print(f"Running Stage 6 Plan Finalization for {target_req_id}...")
    plan = run_stage_6(
        requirement=target_req,
        architecture_decision=s3_output,
        stage_5_output=s5_output,
        client=client,
        run_dir=run_dir,
        document_path=doc_path,
        pipeline_metadata=pipeline_metadata
    )

    print("\n" + "="*80)
    print(f"STAGE 6 FINAL IMPLEMENTATION PLAN ({target_req_id})")
    print("="*80)
    print(f"Plan ID: {plan.plan_id}")
    print(f"Chosen Approach: {plan.chosen_approach}")
    print(f"Rationale: {plan.rationale}")
    print("\nActions list:")
    for a in plan.actions:
        print(f"  - [{a.action_id}] {a.operation_id}: {a.description} (Duration: {a.estimated_duration_seconds}s)")
        if a.depends_on:
            print(f"    Depends on: {', '.join(a.depends_on)}")
    print("="*80)

