import argparse
import sys
from pathlib import Path

from planning.orchestrator import run_planning_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Run the Cord AI planning pipeline on a HubSpot system design document."
    )
    parser.add_argument(
        "document_path",
        type=str,
        help="Path to the system design document (e.g. test_documents/acme.docx)"
    )
    parser.add_argument(
        "--requirement",
        type=str,
        default=None,
        help="The specific requirement ID to plan (e.g. REQ-009). If not specified, defaults to first requirement unless --interactive is set."
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactively select a requirement after extracting them in Stage 1."
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["sonnet", "opus"],
        default="sonnet",
        help="The Anthropic Claude model to use for planning stages (default: sonnet)."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging."
    )
    parser.add_argument(
        "--skip-inspection",
        action="store_true",
        help="Skip the live Stage 4 state inspection and load cached results from a previous run if available."
    )

    args = parser.parse_args()

    doc_path = Path(args.document_path)
    if not doc_path.exists():
        print(f"Error: Document path '{args.document_path}' does not exist.")
        sys.exit(1)

    try:
        run_planning_pipeline(
            document_path=str(doc_path),
            requirement_id=args.requirement,
            output_dir=Path("plans"),
            interactive=args.interactive,
            model_name=args.model,
            verbose=args.verbose,
            skip_inspection=args.skip_inspection
        )
    except KeyboardInterrupt:
        print("\nPipeline run cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nPipeline run failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
