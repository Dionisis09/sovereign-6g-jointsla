"""Full independent verification of the local scale experiment exports."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scalability.validation import verify
if __name__=="__main__":print(verify(ROOT/"results/scalability_30seeds"))
