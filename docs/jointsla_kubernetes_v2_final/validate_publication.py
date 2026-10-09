"""Verify counts, summaries and numbers in the publication artifacts without changing them."""
from pathlib import Path
import csv,json,math,statistics,zipfile,xml.etree.ElementTree as ET,hashlib
O=Path(__file__).resolve().parent;R=O.parents[1]
def rows(name):
 with (O/'tables'/name).open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def check(a,b):assert math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-10),(a,b)
def txt(z,name,namespace):return ' '.join(ET.fromstring(z.read(name)).itertext())
def main():
 manifest_path=O/'PACKAGE_MANIFEST.json'
 if manifest_path.exists():
  manifest=json.loads(manifest_path.read_text())
  for name,r in manifest['files'].items():
   p=O/name;assert p.stat().st_size==r['size'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],name
 C=json.loads((O/'canonical_results.json').read_text());P={x['policy']:x for x in C['policies']}
 runs=rows('all_180_runs.csv');assert len(runs)==180 and sum(int(x['offered']) for x in runs)==230400
 for a,p in P.items():
  rr=[x for x in runs if x['policy']==a];assert len(rr)==30 and len({x['block'] for x in rr})==30
  for k in p:
   if k.endswith('_mean') and k[:-5] in rr[0]:check(p[k],statistics.mean(float(x[k[:-5]]) for x in rr))
   elif k.endswith('_std') and k[:-4] in rr[0]:check(p[k],statistics.stdev(float(x[k[:-4]]) for x in rr))
 paired=rows('paired_sla_comparisons.csv')
 with zipfile.ZipFile(O/'evidence/Kubernetes_v2_complete_evidence.zip') as z:
  assert z.read('prototype/kubernetes/evidence/comparison_v2/paired_comparisons.csv')==(O/'tables/paired_sla_comparisons.csv').read_bytes()
  assert z.read('prototype/kubernetes/evidence/comparison_v2/runs.csv')==(O/'tables/all_180_runs.csv').read_bytes()
 for r,x in zip(paired,C['paired_sla']):
  for k in ['sla_failure_difference_pp','ci95_low_pp','ci95_high_pp','paired_wilcoxon_p']:check(r[k],x[k])
  if x['holm_three_core_comparisons_p'] is None:assert not r['holm_three_core_comparisons_p']
  else:check(r['holm_three_core_comparisons_p'],x['holm_three_core_comparisons_p'])
 categories=rows('failure_attribution.csv');tiers=rows('per_tier_failures.csv')
 for a,p in P.items():
  cc=[x for x in categories if x['policy']==a];assert sum(int(x['count']) for x in cc)==38400
  failed=sum(int(x['count']) for x in cc if x['category']!='completed_on_time');check(failed/384, p['sla_failure_percent_mean'])
  for t,n in [('Gold',12810),('Silver',12810),('Bronze',12780)]:
   rr=next(x for x in tiers if x['policy']==a and x['tier']==t);assert int(rr['offered'])==n
   check(rr['sla_failure_percent'],100*int(rr['failed'])/n);check(rr['sla_failure_percent'],p[t.lower()+'_sla_failure_percent_mean'])
 for x in C['resource_tradeoffs']:
  check(x['increase_percent_of_mean_target_rs'],100*(P['joint']['target_replica_seconds_mean']/P[x['baseline']]['target_replica_seconds_mean']-1))
 summary=[[p['label']]+[f"{p[m+'_mean']:.2f} ± {p[m+'_std']:.2f}" for m in ['sla_failure_percent','p95_completed_latency_ms','rejection_percent','target_replica_seconds']] for p in P.values()]
 ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
 textparts={}
 for stem in ['JointSLA_Final_Technical_Report','JointSLA_Conference_Paper_Draft']:
  with zipfile.ZipFile(O/(stem+'.docx')) as z:
   xml=ET.fromstring(z.read('word/document.xml'));textparts[stem]=' '.join(x.text or '' for x in xml.findall('.//w:t',ns))
   actual=[]
   for row in xml.findall('.//w:tbl/w:tr',ns):actual.append([''.join(x.text or '' for x in cell.findall('.//w:t',ns)) for cell in row.findall('w:tc',ns)])
   for row in summary:assert row in actual,(stem,row)
   assert not ET.fromstring(z.read('word/styles.xml')).findall('.//w:pBdr',ns),'title border residue'
  assert (O/(stem+'.md')).read_text(encoding='utf-8').count('49.89')>0
 with zipfile.ZipFile(O/'JointSLA_Conference_Presentation.pptx') as z:
  slideparts=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml') and '/_rels/' not in n];assert len(slideparts)==14
  notes=[n for n in z.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml') and '/_rels/' not in n];assert len(notes)==14
  textparts['slides']=' '.join(' '.join(x.text or '' for x in ET.fromstring(z.read(n)).findall('.//a:t',ns)) for n in slideparts+notes)
  expected=[('sla_failure_percent',['static','reactive','hpa','joint']),('p95_completed_latency_ms',['reactive','joint']),('rejection_percent',['reactive','joint']),('tiers',['static','reactive','hpa','joint']),('target_replica_seconds',['static','reactive','hpa','joint']),('sla_failure_percent',['joint','joint_sq','reactive_joint'])]
  chartparts=sorted([n for n in z.namelist() if '/charts/chart' in n and n.endswith('.xml') and '/_rels/' not in n]);assert len(chartparts)==6
  for n,(m,arms) in zip(chartparts,expected):
   xml=ET.fromstring(z.read(n));values=[float(v.text) for v in xml.findall('.//c:ser/c:val/c:numRef/c:numCache/c:pt/c:v',ns)]
   exp=[P[a][t+'_sla_failure_percent_mean'] for t in ['gold','silver','bronze'] for a in arms] if m=='tiers' else [P[a][m+'_mean'] for a in arms]
   assert len(values)==len(exp),(n,values,exp)
   for a,b in zip(values,exp):assert abs(a-b)<=5.1e-7,(n,a,b)
 for artifact,text in textparts.items():
  for token in ['49.89','61.43','61.50','62.39','58.84','103.45','65.12','79.63','35.94','34.06','0.158844','230,400']:
   assert token in text,(artifact,token)
  lower=text.lower();assert 'replica-seconds' in lower and 'unmet' in lower and 'exploratory' in lower
  assert ('simulation' in lower or 'simulator' in lower) and ('conditional' in lower or 'excludes rejected' in lower),(artifact,'scope and latency interpretation')
  normalized=text.replace('−','-')
  for token in ['-11.54','-13.98','-9.06','-2.10','-4.84','0.73']:assert token in normalized,(artifact,token)
  assert 'complete within' in lower or 'complete within its audited' in lower
 figures=sorted((O/'figures').glob('*.png'));assert len(figures)==7
 for p in figures:assert p.with_suffix('.pdf').exists()
 receipt={'passed':True,'blocks':30,'trials':180,'offered_outcomes':230400,'policies':6,'native_charts':6,'slides':14,'documents':2,'figures':7,'checks':['run counts and independently recomputed means/sample SD','exact frozen paired table and all-run byte copies','failure and tier count reconciliation','resource ratios','all policy summary rows in both Word files','chart caches against canonical values within six-decimal rounding','shared claims and interpretation in all three artifacts','title border removal','PNG/vector PDF pairs']}
 print(json.dumps(receipt,indent=2));return receipt
if __name__=='__main__':main()
