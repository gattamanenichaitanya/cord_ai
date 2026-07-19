import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Union

import anthropic

from execution.models import ExecutionReport, ExecutionStatus, ActionResult
from execution.executors.api_executor import APIExecutor
from execution.executors.ui_executor import UIExecutor
from execution.tools.vision_locator import VisionLocator
from planning.models import ImplementationPlan, PlanAction


async def execute_plan(
    plan_path_or_obj: Union[str, Path, ImplementationPlan],
    progress_callback = None,
    demo_mode: bool = False,
    dry_run: bool = False,
    stop_on_failure: bool = True,
    model: str = "claude-sonnet-4-6"
) -> ExecutionReport:
    """
    Load a plan (or accept in-memory) and execute every action in dependency order.
    """
    if isinstance(plan_path_or_obj, ImplementationPlan):
        plan = plan_path_or_obj
        plan_path = f"in_memory_{plan.plan_id}.json"
    else:
        plan_path = str(plan_path_or_obj)
        plan_file = Path(plan_path)
        if not plan_file.exists():
            raise FileNotFoundError(f"Plan not found: {plan_path}")
            
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        
        plan = ImplementationPlan(**plan_data)
    
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    run_dir = Path(f"execution_runs/{plan.plan_id}-{timestamp}")
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading plan: {plan_path}")
    print(f"Plan has {len(plan.actions)} actions:")
    
    api_executor = APIExecutor()
    
    # Initialize vision locator
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    vision_locator = VisionLocator(client, model=model)
    ui_executor = UIExecutor(
        vision_locator=vision_locator,
        demo_mode=demo_mode,
        progress_callback=progress_callback
    )
    
    # Check dependencies (just existence)
    action_ids = {a.action_id for a in plan.actions}
    for i, action in enumerate(plan.actions):
        for dep in action.depends_on:
            if dep not in action_ids:
                raise ValueError(f"Action {action.action_id} depends on invalid action: {dep}")
                
        # To determine [API] or [UI], load operation
        op_file = Path("graph/hubspot/operations") / f"{action.operation_id.split('.')[-1]}.json"
        method_str = "UI"
        if op_file.exists():
            with open(op_file, "r", encoding="utf-8") as f:
                op_data = json.load(f)
            if await api_executor.can_execute(op_data):
                method_str = "API"
                
        print(f"  {i+1}. {action.action_id}: {action.description[:40]:<40} [{method_str}]")
        
    print()
    
    results = []
    total_vision_cost = 0.0
    start_time = datetime.now()
    overall_status = ExecutionStatus.SUCCESS
    
    for action in plan.actions:
        op_file = Path("graph/hubspot/operations") / f"{action.operation_id.split('.')[-1]}.json"
        if not op_file.exists():
            print(f"Executing {action.action_id} (UNKNOWN)...")
            print(f"  Warning: Operation file {op_file} not found. Skipping.")
            result = ActionResult(
                action_id=action.action_id,
                operation_id=action.operation_id,
                status=ExecutionStatus.SKIPPED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_seconds=0.0,
                error_message=f"Operation file not found (pruned)."
            )
            results.append(result)
            if progress_callback and hasattr(progress_callback, "on_action_start"):
                progress_callback.on_action_start(action.action_id, action.description, "UNKNOWN")
            if progress_callback and hasattr(progress_callback, "on_action_complete"):
                progress_callback.on_action_complete(action.action_id, result.status, result.duration_seconds)
            continue
            
        with open(op_file, "r", encoding="utf-8") as f:
            op_data = json.load(f)
            
        can_api = await api_executor.can_execute(op_data)
        can_ui = await ui_executor.can_execute(op_data)
        
        executor = None
        method_label = ""
        if can_api:
            executor = api_executor
            method_label = "API"
        elif can_ui:
            executor = ui_executor
            method_label = "UI"
        else:
            print(f"Executing {action.action_id} (UNKNOWN)...")
            print(f"  Error: No executor can handle this operation")
            overall_status = ExecutionStatus.FAILED
            if stop_on_failure:
                break
            continue
            
        print(f"Executing {action.action_id} ({method_label})...")
        if progress_callback and hasattr(progress_callback, "on_action_start"):
            progress_callback.on_action_start(action.action_id, action.description, method_label)
        
        if dry_run:
            print(f"  [Dry Run] Would execute {action.operation_id} via {method_label}")
            result = ActionResult(
                action_id=action.action_id,
                operation_id=action.operation_id,
                status=ExecutionStatus.SKIPPED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_seconds=0.0
            )
            results.append(result)
            if progress_callback and hasattr(progress_callback, "on_action_complete"):
                progress_callback.on_action_complete(action.action_id, result.status, result.duration_seconds)
            continue
            
        result = await executor.execute(action, op_data, run_dir)
        results.append(result)
        
        if method_label == "API":
            if result.status == ExecutionStatus.SUCCESS:
                print("  [SUCCESS] Request successful")
                if result.verification_result and result.verification_result.get("success"):
                    print("  [SUCCESS] Verified")
            else:
                print(f"  [FAILED] Failed: {result.error_message}")
        elif method_label == "UI":
            for step in result.steps:
                mark = "[SUCCESS]" if step.status == ExecutionStatus.SUCCESS else "[FAILED]"
                print(f"  Step {step.step_id}: {step.intent[:50]}... {mark}")
            if result.status == ExecutionStatus.SUCCESS:
                v_reason = "completed"
                if result.verification_result:
                    v_reason = result.verification_result.get("reason", "completed")
                print(f"  [SUCCESS] Verified: {v_reason}")
            else:
                print(f"  [FAILED] Failed: {result.error_message}")
                
        print(f"  Duration: {result.duration_seconds:.1f}s")
        if method_label == "UI":
            healing_count = sum(s.healing_attempts for s in result.steps)
            print(f"  Healing attempts total: {healing_count}")
        print()
        
        if progress_callback and hasattr(progress_callback, "on_action_complete"):
            progress_callback.on_action_complete(action.action_id, result.status, result.duration_seconds)

        if result.status != ExecutionStatus.SUCCESS:
            overall_status = ExecutionStatus.FAILED
            if stop_on_failure:
                break
                
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()
    
    # Calculate costs 
    healing_count = sum(sum(s.healing_attempts for s in r.steps) for r in results)
    total_vision_cost = healing_count * 0.03 # Approx 3 cents per vision call
        
    success_count = sum(1 for r in results if r.status == ExecutionStatus.SUCCESS)
    
    report = ExecutionReport(
        plan_id=plan.plan_id,
        plan_source_path=plan_path,
        run_dir=str(run_dir),
        started_at=start_time,
        completed_at=end_time,
        overall_status=overall_status,
        action_results=results,
        total_duration_seconds=total_duration,
        api_cost_estimate=total_vision_cost,
        summary=f"Executed {len(results)} actions. {success_count} successful."
    )
    
    report_file = run_dir / "report.json"
    report_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    
    print("------------------------------------------")
    print("Plan execution complete")
    print(f"  Total duration: {total_duration:.1f}s")
    print(f"  Successful actions: {success_count}/{len(plan.actions)}")
    print(f"  Failed actions: {len(results) - success_count}")
    print(f"  Vision API cost: ${total_vision_cost:.2f}")
    print(f"  Report saved to: {report_file}")
    
    await ui_executor._cleanup()
    
    if progress_callback and hasattr(progress_callback, "on_plan_complete"):
        progress_callback.on_plan_complete(report)

    return report
