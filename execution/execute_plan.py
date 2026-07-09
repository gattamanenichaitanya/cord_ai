import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="CLI entry point for running a HubSpot plan execution (Day 5)")
    parser.add_argument("plan_path", type=str, help="Path to the implementation plan JSON file")
    args = parser.parse_args()

    print(f"Executing plan: {args.plan_path}")
    # TODO: Implement orchestration flow


if __name__ == "__main__":
    main()
