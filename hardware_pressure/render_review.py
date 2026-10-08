"""Render delivered plot PDFs and make labeled contact sheets for visual review."""
from pathlib import Path
import shutil,subprocess
from PIL import Image,ImageOps,ImageDraw
from .experiment import SWEEP,CAUSAL

def sheet(paths,target):
    columns=3;cell=(700,490);rows=(len(paths)+columns-1)//columns
    canvas=Image.new('RGB',(columns*cell[0],rows*cell[1]),'white');draw=ImageDraw.Draw(canvas)
    for i,path in enumerate(paths):
        pic=Image.open(path).convert('RGB');pic.thumbnail((690,455))
        x=(i%columns)*cell[0];y=(i//columns)*cell[1]
        canvas.paste(pic,(x+(cell[0]-pic.width)//2,y+25));draw.text((x+6,y+4),path.stem,fill='black')
    canvas.save(target)

def render(out):
    figs=out/'figures';pngs=sorted(figs.glob('*.png'))
    sheet(pngs,out/'figure_preview.png')
    executable=shutil.which('pdftoppm')
    if not executable:raise RuntimeError('PDF renderer unavailable')
    folder=out/'pdf_review';folder.mkdir(exist_ok=True)
    for pdf in sorted(figs.glob('*.pdf')):
        subprocess.run([executable,'-png','-singlefile','-scale-to','1400',str(pdf),str(folder/pdf.stem)],check=True,capture_output=True)
    sheet(sorted(folder.glob('*.png')),folder/'contact.png')
    return len(pngs)

if __name__=='__main__':
    for out in (SWEEP,CAUSAL):
        if (out/'report.md').exists():print(out,render(out))
