"""Verify the new experiment without rewriting protected paper results."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from joint_routing.validation import verify

if __name__ == "__main__":
    print(verify(ROOT/"results/joint_routing_30seeds"))
