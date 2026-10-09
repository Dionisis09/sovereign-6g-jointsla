"""Two explicitly owned local labs; never use a global Kubernetes context."""
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LAB=os.getenv('JOINTSLA_LAB','prototype')
if LAB not in ('prototype','validation'): raise ValueError('Unknown owned JointSLA lab')
CLUSTER='jointsla-'+LAB
CACHE=ROOT/('.cache/kubernetes' if LAB=='prototype' else '.cache/kubernetes-validation')
NS='jointsla-prototype'
OFFSET=0 if LAB=='prototype' else 10000
URL=f'http://127.0.0.1:{8091+OFFSET}'
PROM=f'http://127.0.0.1:{9091+OFFSET}'
GRAF=f'http://127.0.0.1:{3001+OFFSET}'
KUBECTL=['kubectl','--kubeconfig',str(CACHE/'config'),'--context','kind-'+CLUSTER,'-n',NS]
