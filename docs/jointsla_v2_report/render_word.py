"""Use the packaged rasterizer with native Word PDF on Windows without LO."""
from pathlib import Path
import importlib.util,shutil,json
from PIL import Image,ImageDraw
BASE=Path(__file__).resolve().parent
SKILL=Path('C:/Users/dioni/.codex/plugins/cache/openai-primary-runtime/documents/26.921.10847/skills/documents')
spec=importlib.util.spec_from_file_location('packaged_renderer',SKILL/'render_docx.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
pdf=BASE/'qa/JointSLA_v2_Experimental_Report.pdf'
def convert(doc_path,user_profile,out_dir,stem,verbose=False):
    destination=Path(out_dir)/(stem+'.pdf');shutil.copy2(pdf,destination)
    return str(destination),'Native Microsoft Word PDF export; bundled LibreOffice unavailable on Windows.'
module.convert_to_pdf=convert
for old in (BASE/'qa').iterdir():
    if old.is_file() and (old.name.startswith('page-') or old.name.startswith('contact_')) and old.suffix=='.png':
        old.unlink()
pages=module.rasterize(str(BASE/'JointSLA_v2_Experimental_Report.docx'),str(BASE/'qa'),150,verbose=False,emit_pdf=False)
for start in range(0,len(pages),9):
    selected=pages[start:start+9];canvas=Image.new('RGB',(1800,3*850),'#dddddd');draw=ImageDraw.Draw(canvas)
    for i,path in enumerate(selected):
        pic=Image.open(path).convert('RGB');pic.thumbnail((585,810));x=(i%3)*600;y=(i//3)*850
        canvas.paste(pic,(x+(600-pic.width)//2,y+30));draw.text((x+10,y+8),Path(path).stem,fill='black')
    canvas.save(BASE/'qa'/f'contact_{start//9+1}.png')
(BASE/'qa/render_receipt.json').write_text(json.dumps(dict(pages=len(pages),engine='Microsoft Word PDF plus packaged render_docx.py rasterizer',dpi=150),indent=2))
print('Rendered pages:',len(pages))
