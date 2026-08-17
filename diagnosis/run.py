"""CLI: python -m diagnosis.run --incident INC-1042"""

from __future__ import annotations

import argparse
import json

from diagnosis.loop import diagnose


def main() -> None:
    parser = argparse.ArgumentParser(description="Run causal diagnosis for a demo incident.")
    parser.add_argument("--incident", required=True, help="Incident id, e.g. INC-1042")
    args = parser.parse_args()
    result = diagnose(args.incident)
    print(
        json.dumps(
            {
                "status": result.status,
                "root_cause_node": result.root_cause_node,
                "confidence": result.confidence,
                "reason": result.reason,
                "record_id": result.record_id,
                "visited_nodes": result.visited_nodes,
                "discrepancy": result.discrepancy,
                "trace": result.trace,
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
