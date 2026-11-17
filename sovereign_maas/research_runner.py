"""One-command, CPU-only Phase 2 replay, training and held-out evaluation."""

import argparse
import json
from pathlib import Path

from .research_data import generate
from .research_models import evaluate, train


def main() -> None:
    parser = argparse.ArgumentParser(description="Sovereign-MaaS simulation-only Phase 2")
    parser.add_argument("--stage", choices=("generate", "train", "evaluate", "all"), default="all")
    parser.add_argument("--output", type=Path, default=Path("results/phase2-v1"))
    args = parser.parse_args()
    result = {}
    if args.stage in ("generate", "all"):
        result["dataset"] = generate(args.output)
    if args.stage in ("train", "all"):
        result["model"] = train(args.output)
    if args.stage in ("evaluate", "all"):
        result["evaluation"] = evaluate(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
