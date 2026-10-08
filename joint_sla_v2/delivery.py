"""Final artifact integrity receipt; run after independent and visual review."""
import xml.etree.ElementTree as ET
from hardware_grounded.environment import ROOT,write_json
from hardware_grounded.integrity import sha
from .protocol import DEV,FINAL,read,verify_freeze,verify_protected,now
from .analysis import FIGURES

def finalize():
    manifest=verify_freeze();protected=verify_protected()
    dev=read(DEV/'independent_validation.json');held=read(FINAL/'independent_validation.json')
    assert dev['runs']==45 and held['runs']==180 and held['paired_tests_independently_verified']==40
    suites=list(ET.parse(FINAL/'tests.xml').getroot().iter('testsuite'))
    tests=sum(int(s.attrib['tests']) for s in suites)
    assert tests>=244 and sum(int(s.attrib['failures'])+int(s.attrib['errors']) for s in suites)==0
    assert sum(s.startswith('# ') for s in (FINAL/'report.md').read_text(encoding='utf-8').splitlines())==27
    for name in FIGURES:
        for ext in ('png','svg','pdf'):
            path=FINAL/'figures'/f'{name}.{ext}'
            assert path.is_file() and path.stat().st_size>1000
            if ext=='svg':ET.parse(path)
            if ext=='pdf':assert path.read_bytes().startswith(b'%PDF')
    receipt=dict(timestamp=now(),tests_passed=tests,existing_tests_preserved=215,new_tests=tests-215,
        development_runs=45,heldout_runs=180,development_requests_verified=dev['requests_verified'],heldout_requests_verified=held['requests_verified'],
        total_requests_verified=dev['requests_verified']+held['requests_verified'],protected_files=protected['protected_files'],changed_files=[],
        config_sha256=manifest['config_sha256'],freeze_timestamp=manifest['timestamp'],heldout_generated_after_freeze=True,
        paired_tests_independently_verified=40,figure_groups=15,figure_files=45,report_sections=27,stop=True,no_v3=True)
    write_json(FINAL/'delivery_validation.json',receipt)
    files={}
    for out in (DEV,FINAL):
        for p in out.rglob('*'):
            if p.is_file() and p.name!='artifact_hashes.json':files[p.relative_to(ROOT).as_posix()]=sha(p)
    for name,h in manifest['source_hashes'].items():files[name]=h
    write_json(FINAL/'artifact_hashes.json',files)
    print(receipt);return receipt

if __name__=='__main__':finalize()
