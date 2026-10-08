"""Small frozen artifacts only. No simulator imports or filesystem writes."""
from pathlib import Path
import json
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {
    'Baseline': 'paper_30seeds', 'Synthetic': 'joint_routing_30seeds',
    'Scalability': 'scalability_30seeds', 'Controller': 'controller_optimization',
    'MJO': 'strong_baseline_30seeds', 'Hardware': 'hardware_grounded',
    'Pressure': 'hardware_pressure_sweep', 'Mechanism': 'hardware_causal_decomposition',
    'Development': 'jointsla_v2_development', 'Held-out': 'jointsla_v2_heldout',
    'Profiling': 'hardware_grounded/profiling',
}

def discover(root=ROOT):
    """Resolve existing paths without renaming or moving evidence."""
    return {k: Path(root) / 'results' / v for k, v in DIRECTORIES.items()}

def source_path(dataset, filename, root=ROOT):
    """Restrict loaders to explicitly selected files inside a source directory."""
    directory = discover(root)[dataset].resolve()
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory):
        raise ValueError('Source path escapes the selected directory')
    return path

@st.cache_data(show_spinner=False)
def _csv(path, stamp):
    return pd.read_csv(path)

def load_csv(dataset, filename='summary_statistics.csv', root=ROOT):
    """Return an empty frame for absent optional evidence; reject huge defaults."""
    path = source_path(dataset, filename, root)
    if not path.exists():
        return pd.DataFrame()
    if path.stat().st_size > 15_000_000:
        raise ValueError('Large request/trajectory data require an explicit lazy view')
    return _csv(str(path), path.stat().st_mtime_ns).copy()

@st.cache_data(show_spinner=False)
def _text(path, stamp):
    return Path(path).read_text(encoding='utf-8')

def load_text(dataset, filename='report.md', root=ROOT):
    path = source_path(dataset, filename, root)
    return _text(str(path), path.stat().st_mtime_ns) if path.exists() else ''

def load_json(dataset, filename, root=ROOT):
    text = load_text(dataset, filename, root)
    return json.loads(text) if text else {}

def raw(dataset, root=ROOT):
    """Seed-level aggregates, never millions of request outcomes."""
    name = 'raw_policy_results.csv' if dataset in ['Baseline', 'Synthetic'] else 'raw_results.csv'
    return load_csv(dataset, name, root)

def filter_frame(frame, **selections):
    out = frame.copy()
    for column, value in selections.items():
        if column in out and value is not None:
            values = value if isinstance(value, (list, tuple, set)) else [value]
            out = out[out[column].isin(values)]
    return out
