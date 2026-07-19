import argparse
import sys
import asyncio
from pathlib import Path

from execution.orchestrator import execute_plan

def main():
    parser = argparse.ArgumentParser(description="CLI entry point for running a HubSpot plan execution (Day 5)")
    parser.add_argument("plan_path", type=str, help="Path to the implementation plan JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Don't make actual changes")
    parser.add_argument("--stop-on-failure", action="store_true", default=True, help="Halt on first failed action (default true)")
    parser.add_argument("--continue-on-failure", action="store_false", dest="stop_on_failure", help="Continue past failures (opposite)")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-6", help="Vision model for self-healing (default sonnet-4-6)")
    args = parser.parse_args()

    asyncio.run(execute_plan(
        plan_path=args.plan_path,
        dry_run=args.dry_run,
        stop_on_failure=args.stop_on_failure,
        model=args.model
    ))


if __name__ == "__main__":
    main()
