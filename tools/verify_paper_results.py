"""Verify exported paper results without rerunning any simulator."""
import argparse
import json
from pathlib import Path
from paper_evaluation.validation import verify

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("results/paper_30seeds"))
    args=parser.parse_args()
    print(json.dumps(verify(args.output),indent=2))
