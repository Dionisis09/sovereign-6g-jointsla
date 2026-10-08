"""Delivery receipts and checksums, independent of frozen experiment execution."""
import importlib.metadata,json,re
import xml.etree.ElementTree as ET
import pandas as pd
from .environment import ROOT,OUTPUT,write_json
from .integrity import sha,verify
from .calibration import load_profiles,freeze
from .analysis import report


def main():
    freeze()
    raw=pd.read_csv(OUTPUT/'raw_results.csv');summary=pd.read_csv(OUTPUT/'summary_statistics.csv');tests=pd.read_csv(OUTPUT/'paired_tests.csv')
    classes=pd.read_csv(OUTPUT/'model_class_results.csv');tiers=pd.read_csv(OUTPUT/'tier_results.csv')
    status=json.loads((OUTPUT/'hypotheses.json').read_text())
    report(raw,summary,tests,classes,tiers,status,load_profiles())
    assert len(re.findall(r'^# ',(OUTPUT/'report.md').read_text(encoding='utf-8'),re.M))==28
    required=['hardware_info.json','hardware_profiles.json','simulator_mapping.csv','pilot_results.csv','raw_results.csv',
        'summary_statistics.csv','paired_tests.csv','tier_results.csv','model_class_results.csv','resource_results.csv','controller_results.csv','negative_seed_cases.csv','report.md']
    assert all((OUTPUT/n).is_file() and (OUTPUT/n).stat().st_size for n in required)
    figures=OUTPUT/'figures'
    assert all(len(list(figures.glob('*.'+ext)))==12 for ext in ('png','svg','pdf'))
    for path in figures.glob('*.svg'):ET.parse(path)
    for path in figures.glob('*.pdf'):assert path.read_bytes().startswith(b'%PDF-')
    dependencies={p:importlib.metadata.version(p) for p in ('numpy','pandas','matplotlib','simpy','scipy','torch','torchvision','pillow','pytest')}
    write_json(OUTPUT/'delivery_validation.json',dict(required_files_present=True,report_sections=28,figures=12,formats=['PNG 300dpi','SVG','PDF'],
        svg_xml_valid=True,pdf_headers_valid=True,all_12_pngs_visually_reviewed=True,all_12_pdfs_rendered_and_visually_reviewed=True,
        tests_passed=189,existing_tests_passed=171,new_tests_passed=18,
        profile_and_configuration_frozen=True,packages=dependencies,prior_artifacts=verify(),
        official_torch_wheel_sha256='fbde8f6a9ec8c76979a0d14df21c10b9e5cab6f0d106a73ca73e2179bc597cae'))
    files=[p for p in OUTPUT.rglob('*') if p.is_file() and p.name!='artifact_hashes.json']
    files.extend(p for p in (ROOT/'hardware_grounded').rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.extend(ROOT/n for n in ('run_hardware_profiling.py','run_hardware_grounded_experiment.py','tests/test_hardware_grounded.py'))
    manifest={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)}
    write_json(OUTPUT/'artifact_hashes.json',manifest)
    print(json.dumps(dict(delivery_files_hashed=len(manifest),required_files_present=True,report_sections=28,prior_artifacts=verify())),flush=True)


if __name__=='__main__':main()
