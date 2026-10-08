"""Detect CUDA hardware or measure three real torchvision architectures."""
import argparse
from hardware_grounded.environment import check


def main():
    from hardware_grounded.integrity import protect
    protect()
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument("--check",action="store_true");mode.add_argument("--profile",action="store_true")
    parser.add_argument("--models",default="mobilenet,resnet50,vit_b16")
    parser.add_argument("--force",action="store_true");args=parser.parse_args()
    info=check()
    if not info["ready_for_gpu_profiling"]:raise SystemExit("STOP: CUDA/PyTorch/torchvision kernel check failed; no GPU profiling or CPU substitution.")
    if args.profile:
        from hardware_grounded.profiling import profile
        profile(tuple(args.models.split(",")),args.force,info)


if __name__=="__main__":main()
