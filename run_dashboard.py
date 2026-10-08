"""Launch local, read-only Streamlit presentation; never execute an experiment."""
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    root=Path(__file__).resolve().parent
    raise SystemExit(subprocess.call([sys.executable,'-m','streamlit','run',str(root/'dashboard'/'app.py'),
        '--server.address','127.0.0.1','--browser.gatherUsageStats','false',*sys.argv[1:]],cwd=root))
