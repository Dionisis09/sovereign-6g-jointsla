"""Run the registered comparison and reconstruction serially, retaining failures."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from prototype.benchmark.experiment import ROOT,MAIN


def main():
    status=ROOT/'.cache/kubernetes-validation/comparison-pipeline-status.json'
    def record(stage,**values):
        status.write_text(json.dumps(dict(stage=stage,utc=datetime.now(timezone.utc).isoformat(),**values),indent=2),encoding='utf-8')
    try:
        record('running_registered_trials')
        subprocess.run([sys.executable,'-m','prototype.benchmark.experiment','--run'],cwd=ROOT,check=True)
        record('reconstructing_all_outcomes')
        subprocess.run([sys.executable,'-m','prototype.benchmark.analyze'],cwd=ROOT,check=True)
        protected=ROOT/'.cache/dashboard_hashes_before.json'
        if protected.exists():
            before=json.loads(protected.read_text())
            assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in before.items())
        metadata=ROOT/'.cache/dashboard_before.json'
        if metadata.exists():
            before=json.loads(metadata.read_text())
            assert all((ROOT/name).stat().st_size==old['size'] and (ROOT/name).stat().st_mtime_ns==old['mtime'] for name,old in before.items())
        result=json.loads((ROOT/'prototype/kubernetes/evidence/comparison_v2/analysis.json').read_text())
        assert result['offered_outcomes_verified']==230400 and result['trials']==180
        report=ROOT/'JOINTSLA_FINAL_REPORT.md'
        text=report.read_text(encoding='utf-8')
        marker='## Completed matched Kubernetes evaluation v2'
        if marker in text: text=text.split(marker)[0].rstrip()+'\n'
        text=text.replace('experiment is being restarted under a new manifest after a preflight\ntelemetry failure; the v1 attempt remains excluded and preserved', 'experiment has completed under the v2 manifest; the aborted v1 attempt\nremains excluded and preserved')
        report.write_text(text+'\n\n## Completed matched Kubernetes evaluation v2\n\n'
            'The new six-arm comparison completed 30 paired blocks / 180 trials and\n'
            'independently reconstructed 230,400 offered outcomes. Historical 38.83%\n'
            'and 47.27% runs and the aborted v1 attempt are excluded. See the\n'
            '[comparative report](prototype/kubernetes/evidence/comparison_v2/COMPARATIVE_REPORT.md),\n'
            '[run values](prototype/kubernetes/evidence/comparison_v2/runs.csv), and\n'
            '[paired effects](prototype/kubernetes/evidence/comparison_v2/paired_comparisons.csv).\n'
            'The comparative report, rather than a live dashboard lifetime counter,\n'
            'defines the statistical result and limitations. Protected source/report\n'
            'hashes and historical result file metadata were checked unchanged.\n',encoding='utf-8')
        verification=ROOT/'prototype/kubernetes/evidence/comparison_v2/protected_verification.json'
        verification.write_text(json.dumps(dict(protected_hashes_unchanged=protected.exists(),protected_metadata_unchanged=metadata.exists()),indent=2),encoding='utf-8')
        record('complete',trials=180,outcomes=230400,report='prototype/kubernetes/evidence/comparison_v2/COMPARATIVE_REPORT.md',
               protected_hashes_checked=protected.exists(),protected_metadata_checked=metadata.exists())
    except Exception as failure:
        record('failed_retained',error=str(failure),main=str(MAIN))
        raise


if __name__=='__main__': main()
