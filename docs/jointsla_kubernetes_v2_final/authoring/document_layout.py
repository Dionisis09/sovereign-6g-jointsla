from pathlib import Path
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
def markdown(pages):
 lines=[]
 for pg in pages:
  lines.append('# '+pg['title']+'\n')
  for b in pg['blocks']:
   if b['type']=='p':lines.append(b['text']+'\n')
   elif b['type']=='h':lines.append('## '+b['text']+'\n')
   elif b['type']=='table':lines.extend(['| '+' | '.join(b['headers'])+' |','| '+' | '.join(['---']*len(b['headers']))+' |']+['| '+' | '.join(r)+' |' for r in b['rows']]+[''])
   else:lines.extend([f"![{b['caption']}](figures/{b['file']}.png)",''])
 return '\n'.join(lines)
def build(O,pages,stem):
 d=Document();sec=d.sections[0];sec.page_width=Inches(8.27);sec.page_height=Inches(11.69);sec.top_margin=Inches(.65);sec.bottom_margin=Inches(.6);sec.left_margin=sec.right_margin=Inches(.8)
 for border in d.styles.element.xpath('.//w:pBdr'):
  border.getparent().remove(border)
 for style in ['Normal','Title','Subtitle','Heading 1','Heading 2','Header','Footer']:
  s=d.styles[style];s.font.name='Calibri';s.font.color.rgb=RGBColor(0,0,0)
 d.styles['Normal'].font.size=Pt(10.5);d.styles['Normal'].paragraph_format.space_after=Pt(7);d.styles['Normal'].paragraph_format.line_spacing=1.08
 for name,size in [('Title',24),('Heading 1',18),('Heading 2',12)]:
  d.styles[name].font.size=Pt(size);d.styles[name].font.bold=True;d.styles[name].paragraph_format.space_after=Pt(9)
 hp=sec.header.paragraphs[0];hp.text='JointSLA   Kubernetes comparison v2';hp.runs[0].font.size=Pt(8)
 fp=sec.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.RIGHT;fp.add_run('9 October 2026   |   ')
 fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');fp._p.append(fld)
 for i,pg in enumerate(pages):
  if i:d.add_page_break()
  d.add_paragraph(pg['title'],'Title' if i==0 else 'Heading 1')
  for b in pg['blocks']:
   if b['type']=='p':d.add_paragraph(b['text'])
   elif b['type']=='h':d.add_paragraph(b['text'],'Heading 2')
   elif b['type']=='fig':
    p=d.add_paragraph();p.paragraph_format.space_after=Pt(3);p.paragraph_format.keep_with_next=True;p.add_run().add_picture(str(O/'figures'/f"{b['file']}.png"),width=Inches(b['width']))
    p=d.add_paragraph(b['caption']);p.paragraph_format.space_after=Pt(8)
    for run in p.runs:run.font.size=Pt(8.5);run.italic=True
   else:
    t=d.add_table(rows=1,cols=len(b['headers']));t.autofit=False
    widths=[2.05]+[(6.67-2.05)/(len(b['headers'])-1)]*(len(b['headers'])-1)
    for cell,w in zip(t.rows[0].cells,widths):cell.width=Inches(w)
    for cell,txt in zip(t.rows[0].cells,b['headers']):cell.text=txt
    for row in b['rows']:
     for cell,txt in zip(t.add_row().cells,row):cell.text=txt
    for ri,row in enumerate(t.rows):
     pr=row._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
     if ri==0:pr.append(OxmlElement('w:tblHeader'))
     for ci,cell in enumerate(row.cells):
      cell.width=Inches(widths[ci]);tc=cell._tc.get_or_add_tcPr();sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'DDE6ED' if ri==0 else ('F4F6F8' if ri%2==0 else 'FFFFFF'));tc.append(sh)
      bord=OxmlElement('w:tcBorders')
      for edge in ['top','left','bottom','right']:
       e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');bord.append(e)
      tc.append(bord);margin=OxmlElement('w:tcMar')
      for edge in ['top','left','bottom','right']:
       e=OxmlElement('w:'+edge);e.set(qn('w:w'),'85');e.set(qn('w:type'),'dxa');margin.append(e)
      tc.append(margin)
      for p in cell.paragraphs:
       p.paragraph_format.space_after=Pt(2);p.paragraph_format.space_before=Pt(2);p.paragraph_format.line_spacing=1.05
       for run in p.runs:run.font.size=Pt(9);run.bold=ri==0
    d.add_paragraph().paragraph_format.space_after=Pt(1)
 d.core_properties.title=pages[0]['title'];d.core_properties.subject='Frozen JointSLA Kubernetes comparison v2';d.core_properties.author=''
 d.save(O/(stem+'.docx'));(O/(stem+'.md')).write_text(markdown(pages),encoding='utf-8');print(stem,len(pages),'planned pages')
