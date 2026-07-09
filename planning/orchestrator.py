import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from planning.claude_client import ClaudeClient
from planning.document_loader import load_document
from planning.models import ImplementationPlan, Stage1Output, Stage2Output, ArchitectureDecision, Stage4Output, Stage5Output, Severity
from planning.stages.stage_1_extraction import run_stage_1
from planning.stages.stage_2_concept_mapping import run_stage_2
from planning.stages.stage_3_architecture_decision import run_stage_3
from planning.stages.stage_4_state_inspection import run_stage_4
from planning.stages.stage_5_gap_detection import run_stage_5
from planning.stages.stage_6_plan_finalization import run_stage_6


def run_planning_pipeline(
    document_path: str,
    requirement_id: str | None = None,
    output_dir: Path = Path("plans"),
    interactive: bool = False,
    model_name: str = "sonnet",
    verbose: bool = False,
    skip_inspection: bool = False
) -> ImplementationPlan:
    # 1. Create run directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path("runs") / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    if verbose:
        print(f"[Verbose] Created run directory: {run_dir}")
        print(f"[Verbose] Model selected: {model_name}")

    # 2. Load the document
    if verbose:
        print(f"[Verbose] Loading document: {document_path}...")
    doc = load_document(document_path)

    # 3. Initialize ClaudeClient
    client_model = "claude-sonnet-4-6" if model_name == "sonnet" else "claude-opus-3"
    client = ClaudeClient(default_model=client_model)

    stages_run = 0

    # 4. Run Stage 1
    print("\n--- Running Stage 1: Requirement Extraction ---")
    s1_output = run_stage_1(doc, client, run_dir)
    stages_run += 1

    # 5. Pick the requirement
    requirement = None
    if requirement_id:
        for r in s1_output.requirements:
            if r.id == requirement_id:
                requirement = r
                break
        if not requirement:
            print(f"Error: Requirement {requirement_id} not found in document.")
            sys.exit(1)
    elif interactive:
        print("\nAvailable Requirements:")
        for idx, r in enumerate(s1_output.requirements, 1):
            print(f"  {idx}. [{r.id}] {r.title} ({r.requirement_type.value})")
        
        while True:
            try:
                choice = input(f"\nSelect a requirement number (1-{len(s1_output.requirements)}): ").strip()
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(s1_output.requirements):
                    requirement = s1_output.requirements[choice_idx]
                    break
                else:
                    print("Invalid choice. Out of range.")
            except ValueError:
                print("Invalid input. Please enter a number.")
    else:
        # Default to the first requirement
        requirement = s1_output.requirements[0]
        print(f"\nNo requirement specified. Defaulting to first requirement: {requirement.id} - '{requirement.title}'")

    print(f"\nSelected Requirement: {requirement.id} - '{requirement.title}'")

    # 6. Run Stage 2
    print("\n--- Running Stage 2: Concept Mapping ---")
    s2_output = run_stage_2(requirement, client, run_dir)
    stages_run += 1

    # Stage 3
    print("\n--- Running Stage 3: Architecture Decision ---")
    s3_output = run_stage_3(requirement, s2_output, client, run_dir)
    stages_run += 1

    # Stage 4
    print("\n--- Running Stage 4: Live State Inspection ---")
    s4_output = None
    if skip_inspection:
        # Try to find a cached stage 4 output for this requirement in any runs directory
        cached_files = sorted(Path("runs").glob(f"**/stage_4_{requirement.id}_output.json"), key=os.path.getmtime, reverse=True)
        if cached_files:
            print(f"Skipping live state inspection. Loading cached file: {cached_files[0]}")
            try:
                with open(cached_files[0], "r", encoding="utf-8") as f:
                    s4_output = Stage4Output.model_validate_json(f.read())
            except Exception as e:
                print(f"Error loading cached Stage 4 output: {e}. Falling back to live inspection...")
        else:
            print("No cached Stage 4 output found. Proceeding to live inspection...")

    if not s4_output:
        s4_output = run_stage_4(requirement, s3_output, run_dir)
    stages_run += 1

    # Stage 5
    print("\n--- Running Stage 5: Gap Detection ---")
    s5_output = run_stage_5(requirement, s3_output, s4_output, client, run_dir)
    stages_run += 1

    # Stage 6
    print("\n--- Running Stage 6: Plan Finalization ---")
    pipeline_metadata = {
        "document_title": doc.title,
        "loaded_at": doc.loaded_at.isoformat(),
        "stages_run": stages_run + 1,
        "verbose_mode": verbose
    }
    
    plan = run_stage_6(
        requirement=requirement,
        architecture_decision=s3_output,
        stage_5_output=s5_output,
        client=client,
        run_dir=run_dir,
        document_path=document_path,
        pipeline_metadata=pipeline_metadata
    )
    stages_run += 1

    # 7. Save final plan to plans/
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / f"plan_{requirement.id}_{timestamp}.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    # 8. Print final summary
    gaps_by_severity = {
        Severity.HIGH: 0,
        Severity.MEDIUM: 0,
        Severity.LOW: 0
    }
    for gap in plan.identified_gaps:
        gaps_by_severity[gap.severity] = gaps_by_severity.get(gap.severity, 0) + 1

    print("\n" + "="*80)
    print("PIPELINE RUN SUMMARY")
    print("="*80)
    print(f"Total stages run:           {stages_run}")
    print(f"Total Claude API cost:      ${client.get_cost_summary()['estimated_cost_usd']:.4f}")
    print(f"Final plan saved to:        {plan_path.resolve()}")
    print(f"Number of actions in plan:  {len(plan.actions)}")
    print(f"Number of gaps identified:  {len(plan.identified_gaps)}")
    print(f"  - High severity:          {gaps_by_severity[Severity.HIGH]}")
    print(f"  - Medium severity:        {gaps_by_severity[Severity.MEDIUM]}")
    print(f"  - Low severity:           {gaps_by_severity[Severity.LOW]}")
    print("="*80)

    return plan
