"""Lightweight validation of aggregate evidence; never repairs or writes sources."""
import pandas as pd
from dashboard.data_loader import discover, load_csv, raw

def validate(root=None):
    from dashboard.data_loader import ROOT
    root=ROOT if root is None else root
    checks=[]
    def add(dataset,check,passed,detail):checks.append(dict(dataset=dataset,check=check,passed=bool(passed),detail=detail))
    for name,path in discover(root).items():
        add(name,'directory',path.is_dir(),str(path.relative_to(root)))
        if name in ['Controller','Profiling']:continue
        filename='regime_summary.csv' if name=='Mechanism' else 'summary_statistics.csv'
        summary=load_csv(name,filename,root)
        required={'policy','metric','n','mean'}
        add(name,'summary schema',required.issubset(summary),filename)
        if not required.issubset(summary):continue
        if name!='Mechanism':
            add(name,'frozen CI schema',{'ci95_lower','ci95_upper'}.issubset(summary),filename)
        keys=[c for c in ['scale','load_multiplier','regime','tier','model_class','policy','metric'] if c in summary]
        add(name,'unique summary keys',not summary.duplicated(keys).any(),', '.join(keys))
        expected=5 if name=='Development' else 10 if name=='Mechanism' else 30
        add(name,'summary seed counts',summary.n.eq(expected).all(),f'Expected {expected} per row')
        frame=raw(name,root)
        if frame.empty:continue
        add(name,'run schema',{'seed','policy'}.issubset(frame),'Seed-level aggregate table')
        if not {'seed','policy'}.issubset(frame):continue
        dims=[c for c in ['scale','load_multiplier','regime','seed'] if c in frame]
        add(name,'unique run keys',not frame.duplicated(dims+['policy']).any(),', '.join(dims+['policy']))
        if 'seed' in frame:
            sizes=frame.groupby([c for c in dims if c!='seed']+['policy']).seed.nunique()
            add(name,'run seed counts',sizes.eq(expected).all(),f'Expected {expected} unique seeds/policy/scope')
        for col in ['traffic_hash','workload_hash','original_arrival_hash']:
            if col in frame:
                add(name,'paired '+col,frame.groupby(dims)[col].nunique(dropna=False).le(1).all(),'Same identifier across policies within each run scope')
    return pd.DataFrame(checks)
