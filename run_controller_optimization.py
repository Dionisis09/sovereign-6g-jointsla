"""Profile, benchmark and exactly verify JointSLA implementation optimization."""
import argparse
import os
from controller_optimization.reference import OUTPUT,ROOT,prepare_reference,profile,verify_protected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    for name in ("profile","validate-equivalence","benchmark","full-validation","all"):
        mode.add_argument("--"+name,action="store_true")
    args=parser.parse_args();os.chdir(ROOT);prepare_reference()
    from controller_optimization.optimized import OptimizedMeasured
    from controller_optimization.validation import golden_equivalence,full_validation
    from controller_optimization.benchmark import benchmark,memory_profile,reassess_h4
    if args.profile or args.all:profile(OptimizedMeasured,"after")
    if args.validate_equivalence or args.all or not (OUTPUT/"equivalence_validation.csv").exists():golden_equivalence()
    if args.benchmark or args.all:benchmark();memory_profile()
    if args.full_validation or args.all:full_validation()
    if (OUTPUT/"controller_performance_before_after.csv").exists() and (OUTPUT/"validation.json").exists():
        reassess_h4()
        from controller_optimization.presentation import create
        from controller_optimization.audit import verify
        create();verify()
    verify_protected()
    print(f"Completed requested stage. Output: {OUTPUT}",flush=True)


if __name__=="__main__":main()
