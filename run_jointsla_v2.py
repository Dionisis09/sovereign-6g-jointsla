"""One development candidate, explicit freeze, then untouched held-out cohort."""
import argparse
from joint_sla_v2.protocol import DEV,FINAL,freeze,verify_freeze,verify_protected
from joint_sla_v2.experiment import execute

def main():
    p=argparse.ArgumentParser(description=__doc__)
    phase=p.add_mutually_exclusive_group(required=True)
    phase.add_argument('--development',action='store_true');phase.add_argument('--freeze',action='store_true');phase.add_argument('--held-out',action='store_true')
    p.add_argument('--reuse-results',action='store_true');p.add_argument('--force',action='store_true')
    a=p.parse_args();print(verify_protected(),flush=True)
    if a.freeze:print(freeze());return
    selected='development' if a.development else 'heldout'
    if selected=='heldout':verify_freeze()
    raw=execute(selected,a.reuse_results,a.force)
    from joint_sla_v2.analysis import analyze
    analyze(raw,DEV if a.development else FINAL,selected)
    print(verify_protected(),flush=True)
    if selected=='heldout':print(verify_freeze()['config_sha256'],flush=True)

if __name__=='__main__':main()
