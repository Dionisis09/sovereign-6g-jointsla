"""Verify all controller-optimization exports without rerunning the experiment."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller_optimization.audit import verify
if __name__=="__main__":print(verify())
