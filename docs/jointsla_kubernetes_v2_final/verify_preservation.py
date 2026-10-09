"""Read-only SHA-256 verification of the final archive and original frozen files."""
from pathlib import Path
import hashlib,json,zipfile,argparse
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--originals',action='store_true',help='Also verify original v2 and all historical result files in the project root')
 p.add_argument('--receipt',type=Path);args=p.parse_args()
 out=Path(__file__).resolve().parent;root=out.parents[1];seal=json.loads((out/'evidence/V2_SOURCE_SEAL.json').read_text())
 archive=out/'evidence/Kubernetes_v2_complete_evidence.zip';assert sha(archive)==seal['archive_sha256'],'archive checksum changed'
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None;assert set(z.namelist())==set(seal['files'])
  for name,r in seal['files'].items():assert hashlib.sha256(z.read(name)).hexdigest()==r['sha256'],name
 result={'archive_members_verified':len(seal['files']),'archive_sha256':seal['archive_sha256'],'v2_originals_verified':0,'historical_originals_verified':0,'all_checks_passed':False}
 print('Archive verified:',len(seal['files']),'members',flush=True)
 if args.originals:
  for name,r in seal['files'].items():assert sha(root/name)==r['sha256'],name
  result['v2_originals_verified']=len(seal['files'])
  hist=json.loads((out/'evidence/HISTORICAL_RESULTS_SEAL.json').read_text())
  for i,(name,r) in enumerate(hist['files'].items()):
   f=root/name;assert sha(f)==r['sha256'],name;assert f.stat().st_size==r['size'] and f.stat().st_mtime_ns==r['mtime_ns'],name
   if (i+1)%5000==0:print('Historical originals verified:',i+1,flush=True)
  result['historical_originals_verified']=len(hist['files'])
 result['all_checks_passed']=True
 if args.receipt:args.receipt.write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
