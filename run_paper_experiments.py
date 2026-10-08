"""Reproduce main paired experiments and their complete statistical evaluation."""
import argparse
from dataclasses import replace, asdict
import hashlib
from pathlib import Path
import os
from catalyst.reused import digest, write_json
from dynamic_placement.config import Config
from paper_evaluation.accounting import validate_pairing
from paper_evaluation.experiments import ROOT, load_or_run
from paper_evaluation.statistics import summarize, paired_analysis, BOOTSTRAP_SEED, RESAMPLES
from paper_evaluation.supplementary import analyze_existing
from paper_evaluation.figures import create
from paper_evaluation.reporting import generate
from paper_evaluation.validation import verify


def parse_seeds(value):
    """Inclusive start:end; exactly 30 independent integer seeds."""
    try:
        start,end=map(int,value.split(":"))
    except (ValueError,TypeError):
        raise argparse.ArgumentTypeError("use inclusive start:end, e.g. 1:30") from None
    if start<0 or end-start+1!=30:
        raise argparse.ArgumentTypeError("exactly 30 consecutive nonnegative seeds required")
    return list(range(start,end+1))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds",type=parse_seeds,default=parse_seeds("1:30"))
    parser.add_argument("--config",type=Path,default=ROOT/"dynamic_placement/config.json")
    parser.add_argument("--output",type=Path,default=ROOT/"results/paper_30seeds")
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--reuse-results",action="store_true")
    mode.add_argument("--force",action="store_true")
    args=parser.parse_args()
    output=args.output.resolve()
    config=replace(Config.load(args.config.resolve()),first_seed=args.seeds[0],trials=len(args.seeds))
    os.chdir(ROOT)
    output.mkdir(parents=True,exist_ok=True)
    sources=[Path(__file__).resolve(),*(ROOT/"paper_evaluation").glob("*.py"),ROOT/"requirements-paper.txt"]
    write_json(output/"analysis_protocol.json",dict(bootstrap_seed=BOOTSTRAP_SEED,resamples=RESAMPLES,
               confidence_level=.95,ci_method="percentile bootstrap of seed means",
               comparisons="3 baselines x 4 primary metrics; two-sided Wilcoxon; Holm family=12",
               effect="paired rank-biserial; positive=baseline minus proposed improvement",
               relative="100*(mean baseline - mean proposed)/mean baseline",
               rounding="12 decimal places for signed ranks and win/tie/loss classification",
               source_hashes={p.relative_to(ROOT).as_posix():digest(p.read_text(encoding="utf-8")) for p in sorted(sources)}))
    raw=load_or_run(config,args.seeds,output,reuse=args.reuse_results,force=args.force)
    validate_pairing(raw,args.seeds)
    summarize(raw).to_csv(output/"summary_statistics.csv",index=False)
    tests,differences=paired_analysis(raw,args.seeds)
    tests.to_csv(output/"paired_tests.csv",index=False)
    differences.to_csv(output/"paired_seed_differences.csv",index=False)
    print("Main statistics exported; verifying and reusing supplemental runs (no simulation rerun).",flush=True)
    analyze_existing(output,ROOT/"results/dynamic_scenarios",ROOT/"results/capacity_sweep")
    create(output)
    generate(output,config,args.seeds)
    verification=verify(output)
    manifest={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(output.rglob("*")) if p.is_file() and p.name!="artifact_hashes.json"}
    write_json(output/"artifact_hashes.json",manifest)
    print(f"Complete: {verification['successful_runs']} runs; {verification['request_outcomes_checked']:,} request outcomes independently verified.",flush=True)
    print(f"Report: {output/'report.md'}",flush=True)


if __name__=="__main__":
    main()
