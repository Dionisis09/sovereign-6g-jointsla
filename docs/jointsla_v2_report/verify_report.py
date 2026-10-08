"""Read-only completeness audit of the final Word document and source assets."""
from pathlib import Path
from collections import Counter
from zipfile import ZipFile
import hashlib,json,re
from docx import Document
from lxml import etree
from pypdf import PdfReader

base=Path(__file__).resolve().parent
manifest=json.loads((base/'build_manifest.json').read_text(encoding='utf-8'))
target=Path(manifest['document'])
digest=lambda data:hashlib.sha256(data).hexdigest()
assert digest(Path(manifest['source_report']).read_bytes())==manifest['source_report_sha256']
doc=Document(target)
assert len(doc.inline_shapes)==15 and len(doc.tables)==45
headings=[p.text for p in doc.paragraphs if p.style.name=='Heading 1']
assert len(headings)==27
captions=[p.text for p in doc.paragraphs if p.text.startswith('Figure ') and p.style.name=='Caption']
assert [int(re.match(r'Figure (\d+)',p)[1]) for p in captions]==list(range(1,16))
with ZipFile(target) as z:
    media=[z.read(n) for n in z.namelist() if n.startswith('word/media/')]
    media_hashes=Counter(digest(data) for data in media)
    original_hashes=Counter(item['sha256'] for item in manifest['figures'])
    assert media_hashes==original_hashes
    for item in manifest['figures']:
        assert digest(Path(item['source']).read_bytes())==item['sha256']
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    styles=etree.fromstring(z.read('word/styles.xml'))
    xml=etree.fromstring(z.read('word/document.xml'))
    assert not styles.xpath('//w:pBdr',namespaces=ns)
    assert not xml.xpath('//w:pBdr',namespaces=ns)
    instructions=' '.join(xml.xpath('//w:instrText/text()',namespaces=ns))
    assert 'TOC' in instructions and len(re.findall(r'PAGEREF\s+fig_\d+',instructions))==15
    assert len(xml.xpath('//w:tblHeader',namespaces=ns))==45

# Every original numeric table cell survives the layout transformations. Load
# grouping labels and hypothesis flags are converted intentionally to headings
# and Passed/Failed labels; these are checked independently above and below.
number=re.compile(r'(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?')
expected=Counter()
source=Path(manifest['source_report']).read_text(encoding='utf-8')
for block in re.findall(r'(?:^\|[^\n]+\n)+',source,re.M):
    lines=block.strip().splitlines()
    headers=[x.strip() for x in lines[0].strip('|').split('|')]
    for line in lines[2:]:
        for key,value in zip(headers,line.strip('|').split('|')):
            if key in ('load_multiplier','policy','comparator','hypothesis','passed'):
                continue
            expected.update(number.findall(value))
actual=Counter()
for table in doc.tables:
    for row in table.rows[1:]:
        for cell in row.cells:
            actual.update(number.findall(cell.text))
missing=expected-actual
assert not missing,dict(missing)
assert any(row.cells[0].text=='V2-H3' and row.cells[1].text=='Failed' for table in doc.tables for row in table.rows)
assert any(row.cells[0].text=='V2-H4' and row.cells[1].text=='Failed' for table in doc.tables for row in table.rows)

pdf=PdfReader(base/'qa/JointSLA_v2_Experimental_Report.pdf')
texts=[page.extract_text() or '' for page in pdf.pages]
assert len(texts)==30 and all(len(text)>100 for text in texts)
assert not any('Error! Reference source not found' in text for text in texts)
(base/'qa/rendered_text.txt').write_text('\n\n'.join(f'PAGE {i+1}\n{text}' for i,text in enumerate(texts)),encoding='utf-8')
receipt=dict(document=str(target),sha256=digest(target.read_bytes()),pages=len(texts),technical_sections=27,
             original_figures_preserved_byte_for_byte=15,tables=45,numeric_table_tokens_verified=sum(expected.values()),
             source_report_unchanged=True,source_figures_unchanged=True,sequential_captions=True,
             updated_contents_and_figure_page_fields=True,no_blank_pages=True,
             a11y=json.loads((base/'qa/a11y_report.json').read_text(encoding='utf-8')))
(base/'qa/completeness_receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='a11y'},ensure_ascii=False))
