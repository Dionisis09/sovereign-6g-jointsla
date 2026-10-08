"""Validate existing strong-baseline exports without rerunning simulation."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from strong_baseline.validation import verify
if __name__=="__main__":print(verify())
