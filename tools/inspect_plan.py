import argparse
import sys
from pathlib import Path
from datetime import datetime

# Reconfigure stdout/stderr to UTF-8 to prevent encoding errors on Windows terminal
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Add the project root to sys.path so we can import models
sys.path.append(str(Path(__file__).resolve().parent.parent))

from planning.models import ImplementationPlan, Severity


def inspect_plan(plan_path: Path):
    if not plan_path.exists():
        print(f"Error: Plan file '{plan_path}' does not exist.")
        sys.exit(1)

    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = ImplementationPlan.model_validate_json(f.read())
    except Exception as e:
        print(f"Error parsing plan JSON: {e}")
        sys.exit(1)

    print("\n" + "="*80)
    print(f"IMPLEMENTATION PLAN INSPECTOR: {plan.requirement_id}")
    print("="*80)
    
    # Header & Metadata
    print(f"Plan ID:          {plan.plan_id}")
    print(f"Requirement:      {plan.requirement_id} - {plan.requirement_title}")
    print(f"Created At:       {plan.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Source Document:  {plan.document_source}")
    print(f"Approval Status:  {'APPROVED' if plan.approved else 'PENDING REVIEW'}")
    if plan.approval_notes:
        print(f"Approval Notes:   {plan.approval_notes}")
        
    print("\n" + "-"*80)
    print("ARCHITECTURAL APPROACH")
    print("-"*80)
    print(f"Approach:\n{plan.chosen_approach}\n")
    print(f"Rationale:\n{plan.rationale}")

    print("\n" + "-"*80)
    print("ACTION SEQUENCE (ORDERED BY DEPENDENCY)")
    print("-"*80)
    if not plan.actions:
        print("No actions in this plan.")
    else:
        for idx, action in enumerate(plan.actions, 1):
            print(f"{idx}. [{action.action_id}] {action.operation_id}")
            print(f"   Description: {action.description}")
            if action.parameters:
                print(f"   Parameters:  {action.parameters}")
            if action.depends_on:
                print(f"   Depends On:  {', '.join(action.depends_on)}")
            print(f"   Est. Duration: {action.estimated_duration_seconds}s")
            print()

    print("-"*80)
    print("IDENTIFIED GAPS & EXECUTION RISKS")
    print("-"*80)
    if not plan.identified_gaps:
        print("No gaps identified.")
    else:
        # Group gaps by severity
        gaps_by_severity = {
            Severity.HIGH: [],
            Severity.MEDIUM: [],
            Severity.LOW: []
        }
        for gap in plan.identified_gaps:
            gaps_by_severity[gap.severity].append(gap)

        for severity in [Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            gaps = gaps_by_severity[severity]
            if gaps:
                print(f"\n[{severity.value.upper()} SEVERITY]")
                for gap in gaps:
                    block_status = "BLOCKS EXECUTION" if gap.blocks_execution else "ADVISORY"
                    print(f"  * {gap.title} ({block_status})")
                    print(f"    ID: {gap.gap_id}")
                    if gap.referenced_gotcha:
                        print(f"    Referenced Gotcha: {gap.referenced_gotcha}")
                    print(f"    Description: {gap.description}")
                    print(f"    Suggested Resolution: {gap.suggested_resolution}")
                    print()

    print("-"*80)
    print("RUN METADATA & TELEMETRY")
    print("-"*80)
    stages_run = plan.pipeline_metadata.get("stages_run", "N/A")
    stage_6_tokens = plan.pipeline_metadata.get("stage_6_tokens", 0)
    exec_order_rationale = plan.pipeline_metadata.get("execution_order_rationale", "N/A")
    
    print(f"Total Pipeline Stages Run: {stages_run}")
    print(f"Stage 6 LLM Token Usage:   {stage_6_tokens} tokens")
    print(f"Execution Order Rationale: {exec_order_rationale}")
    print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect and print a generated ImplementationPlan in human-readable CLI layout."
    )
    parser.add_argument(
        "plan_path",
        type=str,
        help="Path to the plan JSON file"
    )
    args = parser.parse_args()

    inspect_plan(Path(args.plan_path))


if __name__ == "__main__":
    main()
