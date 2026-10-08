"""Repackage the complete frozen report and its 15 original figures into Word."""
from pathlib import Path
import re,json,hashlib
from collections import defaultdict
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START,WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'results/jointsla_v2_heldout'
OUT=Path(__file__).resolve().parent
TARGET=OUT/'JointSLA_v2_Experimental_Report.docx'
doc=Document()
POLICIES=['sla_aware','joint_sla_v1','joint_sla_v2']
POLICY_NAMES={'sla_aware':'SLA-aware','joint_sla_v1':'JointSLA-v1','joint_sla_v2':'JointSLA-v2'}
short={'sla_breach_rate':'Aggregate SLA breach rate','Gold_breach_rate':'Gold breach rate','Silver_breach_rate':'Silver breach rate','Bronze_breach_rate':'Bronze breach rate',
 'mean_request_latency_ms':'Mean request latency ms','median_latency_ms':'Median request latency ms','p95_latency_ms':'p95 latency ms','p99_latency_ms':'p99 latency ms',
 'average_vram_residency_gib':'Average VRAM residency GiB','peak_pool_vram_gib':'Peak pool VRAM GiB','controller_decision_mean_ms':'Mean decision time ms','controller_decision_median_ms':'Median decision time ms',
 'controller_decision_p95_ms':'p95 decision time ms','controller_total_instrumented_mean_ms':'Mean instrumented total ms','controller_total_instrumented_p95_ms':'p95 instrumented total ms',
 'wall_clock_seconds':'Simulation wall time seconds','preburst_active_replicas':'Ready replicas per service before burst','recovery_window_breach_rate':'Recovery window breach rate',
 'mean_recovery_after_burst_slots':'Recovery after burst slots conditional','scaleout_censored_fraction':'Scaleout censoring fraction','recovery_censored_fraction':'Recovery censoring fraction',
 'cold_exposure_service_seconds':'Unavailable exposure service seconds','mean_required_warm_replicas':'Mean required warm replicas per service','mean_actual_ready_replicas':'Mean actual ready replicas per service',
 'headroom_deficit_frequency':'Headroom deficit frequency','service_seconds_below_required':'Service seconds below required warm capacity','prevented_scale_ins_Gold':'Prevented Gold scale ins',
 'prevented_scale_ins_due_to_headroom':'Prevented scale ins due to headroom','scaleouts_during_cold_exposure':'Scaleouts during cold exposure',
 'gold_repair_scaleouts_proposed':'Proposed Gold repair scaleouts','gold_repair_scaleouts_accepted':'Accepted Gold repair scaleouts'}

FIGS=[
 ('01_sla_1x','Aggregate SLA breaches at 1x load','Mean breach rate across 30 paired held-out seeds. Error bars show 95% bootstrap CIs of seed means.'),
 ('02_gold_1x','Gold SLA breaches at 1x load','Gold protection lowers breaches relative to v1; a statistically unresolved baseline comparison does not establish equivalence.'),
 ('03_p95_1x','Request p95 latency at 1x load','Run-level request latency quantiles are averaged across seeds. These are not pooled request quantiles.'),
 ('04_sla_2x','Aggregate SLA breaches at 2x load','The high-pressure regime shows a higher aggregate breach rate for v2 than either comparator.'),
 ('05_p95_2x','Request p95 latency at 2x load','The v1 tail-latency advantage is lost with v2. Error bars show uncertainty across seed means.'),
 ('06_p99_2x','Request p99 latency at 2x load','The v2 p99 is substantially higher under pressure; the paired analysis is reported in the latency section.'),
 ('07_replicas','Average replica occupancy across loads','Occupancy is integrated over the unchanged 10 second orchestration horizon.'),
 ('08_vram','Average VRAM residency across loads','Time-integrated VRAM residency divided by the observation horizon, in GiB.'),
 ('09_actions','Accepted orchestration actions across loads','All policies retain the same maximum of two accepted actions per slot.'),
 ('10_sla_vs_replicas','Aggregate SLA and replica tradeoff','Per-seed points, policy means and marginal 95% bootstrap CIs. No continuous or globally optimal frontier is inferred.'),
 ('11_gold_vs_replicas','Gold SLA and replica tradeoff','Gold improvement relative to v1 is accompanied by a larger warm replica pool.'),
 ('12_p95_vs_vram','Request p95 and VRAM tradeoff','The two pressure regimes reveal different performance and resource costs.'),
 ('13_ready_replicas_before_burst','Ready replica capacity before bursts','Readiness is sampled at the control snapshot immediately before each retrospectively identified burst.'),
 ('14_recovery_breaches','SLA breaches during burst recovery','Each seed aggregates its recovery cohorts. Censored recovery cases and cohort definitions are disclosed in the text.'),
 ('15_controller_overhead','Controller decision overhead','Per-run mean and p95 wall times are averaged across seeds. The dashed line marks the 10 ms mean limit.')]
order=['01_sla_1x','04_sla_2x','02_gold_1x','03_p95_1x','05_p95_2x','06_p99_2x',
       '07_replicas','08_vram','09_actions','13_ready_replicas_before_burst','14_recovery_breaches',
       '15_controller_overhead','10_sla_vs_replicas','11_gold_vs_replicas','12_p95_vs_vram']
FIGS=sorted(FIGS,key=lambda item:order.index(item[0]))
FIG_INDEX={name:(i+1,title,caption) for i,(name,title,caption) in enumerate(FIGS)}
INSERT={'Aggregate SLA':['01_sla_1x','04_sla_2x'],'Gold / Silver / Bronze':['02_gold_1x'],
 'Mean / p95 / p99':['03_p95_1x','05_p95_2x','06_p99_2x'],'Resource Cost':['07_replicas','08_vram','09_actions'],
 'Burst Recovery':['13_ready_replicas_before_burst','14_recovery_breaches'],'Controller Overhead':['15_controller_overhead'],
 'Performance-Resource Frontier':['10_sla_vs_replicas','11_gold_vs_replicas','12_p95_vs_vram']}
WIDE={'10_sla_vs_replicas','11_gold_vs_replicas','12_p95_vs_vram','15_controller_overhead'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def label(key):return short.get(key,key.replace('_',' ').strip().capitalize())
def readable(s):
    for a,b in [('seeds1','seeds 1'),('seeds31','seeds 31'),('seeds101','seeds 101'),('SLA25','SLA 25'),('baseline15','baseline 15'),('Gold35','Gold 35'),('vs22','vs 22'),('vs21','vs 21'),('was1','was 1'),('vs1','vs 1'),('max3','maximum 3'),('budget2','budget 2'),('requires3','requires 3'),('Nodes10','Nodes 10'),('services40','services 40'),('slots100','slots 100'),('to40','to 40'),('real5G','real 5G'),('max(preburst backlog,1)','max(preburst backlog, 1)'),('class cold readiness','class cold readiness')]:s=s.replace(a,b)
    s=re.sub(r'([,;])(?=[A-Za-z])',r'\1 ',s)
    s=s.replace('all40','all 40').replace('across two loads =6','across two loads = 6')
    s=re.sub(r'\b(breaches|multiplier|Bronze|floor|floors|denominator|remains|marginal|reaches|Fixed|exploratory|optional|by|and|use|seed)(?=\d)',r'\1 ',s)
    for a,b in [('only,0.5','only, 0.5'),('×,45','×, 45'),('v2,1×','v2, 1×'),('×:180','×: 180'),(';3,046','; 3,046'),('seeds.10000','seeds. 10000'),('resamples,95','resamples, 95'),('p95×2loads=6','p95 × 2 loads = 6'),('actions×2loads=14','actions × 2 loads = 14'),('service×control','service × control'),('slots×.1','slots × 0.1')]:s=s.replace(a,b)
    s=re.sub(r':(?=[A-Za-z])',': ',s)
    s=re.sub(r'\s*([≤≥])\s*',r' \1 ',s)
    return s

def field(p,code,display=''):
    r=p.add_run();begin=OxmlElement('w:fldChar');begin.set(qn('w:fldCharType'),'begin');r._r.append(begin)
    instr=OxmlElement('w:instrText');instr.set(qn('xml:space'),'preserve');instr.text=code;r._r.append(instr)
    sep=OxmlElement('w:fldChar');sep.set(qn('w:fldCharType'),'separate');r._r.append(sep)
    p.add_run(display)
    end=OxmlElement('w:fldChar');end.set(qn('w:fldCharType'),'end');p.add_run()._r.append(end)

def bookmark(p,name,number):
    a=OxmlElement('w:bookmarkStart');a.set(qn('w:id'),str(number));a.set(qn('w:name'),name)
    b=OxmlElement('w:bookmarkEnd');b.set(qn('w:id'),str(number));p._p.insert(0,a);p._p.append(b)

def section(landscape=False):
    s=doc.add_section(WD_SECTION_START.NEW_PAGE)
    s.orientation=WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    s.page_width=Inches(11.69 if landscape else 8.27);s.page_height=Inches(8.27 if landscape else 11.69)
    s.top_margin=s.bottom_margin=Inches(.65);s.left_margin=s.right_margin=Inches(.6)
    s.header_distance=s.footer_distance=Inches(.28);s.different_first_page_header_footer=False
    return s

def para(text='',style=None):
    p=doc.add_paragraph(style=style)
    for i,part in enumerate(re.split(r'(`[^`]+`)',readable(text))):
        if part.startswith('`') and part.endswith('`'):
            r=p.add_run(part[1:-1]);r.font.name='Consolas';r.font.size=Pt(8.5)
        else:p.add_run(part)
    return p

def heading(text,level=1):return doc.add_paragraph(text,style=f'Heading {level}')

table_count=0
def table(headers,rows,widths=None,size=9.5):
    global table_count
    table_count+=1
    p=para(f'Table {table_count}  {current_title}',style='Caption');p.paragraph_format.keep_with_next=True
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    widths=widths or ([2.85]+[1.4]*(len(headers)-1) if len(headers)==4 else [2.55,4.5] if len(headers)==2 else [7.05/len(headers)]*len(headers))
    for col,w in zip(t.columns,widths):col.width=Inches(w)
    for row_index,values in enumerate([headers]+list(rows)):
        cells=t.rows[0].cells if row_index==0 else t.add_row().cells
        trpr=cells[0]._tc.getparent().get_or_add_trPr()
        cant=OxmlElement('w:cantSplit');trpr.append(cant)
        if row_index==0:
            repeat=OxmlElement('w:tblHeader');trpr.append(repeat)
        for j,(cell,value,w) in enumerate(zip(cells,values,widths)):
            cell.width=Inches(w);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=cell._tc.get_or_add_tcPr();mar=OxmlElement('w:tcMar')
            for edge in ('top','bottom','left','right'):
                item=OxmlElement('w:'+edge);item.set(qn('w:w'),'75');item.set(qn('w:type'),'dxa');mar.append(item)
            tcpr.append(mar)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'243746' if row_index==0 else 'F1F4F6' if row_index%2==0 else 'FFFFFF');tcpr.append(shade)
            cell.text=str(value);p=cell.paragraphs[0];p.alignment=WD_ALIGN_PARAGRAPH.LEFT if j==0 or len(headers)==2 else WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after=Pt(0);p.paragraph_format.space_before=Pt(0);p.paragraph_format.line_spacing=1.05
            p.paragraph_format.keep_with_next=row_index==0
            for r in p.runs:r.font.size=Pt(size);r.font.color.rgb=RGBColor.from_string('FFFFFF' if row_index==0 else '000000');r.bold=row_index==0
    borders=OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
    t._tbl.tblPr.append(borders)
    para().paragraph_format.space_after=Pt(0)
    return t

def json_table(value,prefix=''):
    rows=[]
    def flatten(v,path=''):
        if isinstance(v,dict):
            for k,x in v.items():flatten(x,(path+' '+k).strip())
        else:rows.append([label(path),json.dumps(v,ensure_ascii=False) if isinstance(v,(list,bool)) else str(v)])
    flatten(value,prefix);table(['Record field','Value'],rows,size=9)

def source_table(lines):
    headers=[s.strip() for s in lines[0].strip('|').split('|')]
    records=[dict(zip(headers,[s.strip() for s in line.strip('|').split('|')])) for line in lines[2:]]
    if 'policy' in headers and 'load_multiplier' in headers:
        for load in dict.fromkeys(r['load_multiplier'] for r in records):
            group=[r for r in records if r['load_multiplier']==load];heading(f'{load}x Load',2)
            if len(group)==3 and set(r['policy'] for r in group)==set(POLICIES):
                by={r['policy']:r for r in group};metrics=[k for k in headers if k not in ('policy','load_multiplier')]
                table(['Metric',*[POLICY_NAMES[p] for p in POLICIES]],[[label(k),*[by[p][k] for p in POLICIES]] for k in metrics])
            else:
                for row in group:table(['Metric','JointSLA-v2'],[[label(k),row[k]] for k in headers if k not in ('policy','load_multiplier')])
    elif 'delta_v2_minus_comparator' in headers:
        grouped=defaultdict(list)
        for r in records:grouped[(r['load_multiplier'],r['comparator'])].append(r)
        for (load,comp),group in grouped.items():
            heading(f'{load}x Load Compared With {POLICY_NAMES[comp].replace("-"," ")}',2)
            rows=[[label(r['metric']),f"{r['delta_v2_minus_comparator']}\n[{r['delta_ci95_lower']}, {r['delta_ci95_upper']}]",r['p_value'],r['p_value_holm'],r['rank_biserial_correlation'],f"{r['wins']} / {r['ties']} / {r['losses']}"] for r in group]
            table(['Metric','Delta and 95% CI','Wilcoxon p','Holm p','RBC','Wins ties losses'],rows,[1.6,2.3,.8,.8,.6,.95],size=9)
    elif 'ratio' in headers:
        grouped=defaultdict(list)
        for r in records:grouped[(r['load_multiplier'],r['comparator'])].append(r)
        for (load,comp),group in grouped.items():
            heading(f'{load}x Ratios Compared With {POLICY_NAMES[comp].replace("-"," ")}',2)
            table(['Metric','Ratio','95% CI','Method and resamples'],[[label(r['metric']),r['ratio'],f"[{r['ci95_lower']}, {r['ci95_upper']}]",r['method']+'; '+r['resamples']] for r in group],[2,1,1.6,2.45],size=9)
    elif headers==['hypothesis','passed']:
        table(['Hypothesis','Outcome'],[[r['hypothesis'],'Passed' if r['passed']=='1' else 'Failed'] for r in records])
    else:table([label(h) for h in headers],[[POLICY_NAMES.get(r[h],label(r[h]) if h=='metric' else r[h]) for h in headers] for r in records],size=9.5)

def math_run(text):
    r=OxmlElement('m:r');t=OxmlElement('m:t');t.text=text;r.append(t);return r
def fraction(num,den):
    f=OxmlElement('m:f');n=OxmlElement('m:num');n.append(math_run(num));d=OxmlElement('m:den');d.append(math_run(den));f.append(n);f.append(d);return f
def equation():
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    mp=OxmlElement('m:oMathPara');m=OxmlElement('m:oMath')
    for node in [math_run('required = min(3, max(floor, ⌈factor × max('),fraction('qL','h'),math_run(', '),fraction('(q + λR)L','R + h'),math_run(')⌉))')]:m.append(node)
    mp.append(m);p._p.append(mp)
    p.paragraph_format.space_before=Pt(8);p.paragraph_format.space_after=Pt(10)

figures_added=[]
def figure(name):
    number,title,description=FIG_INDEX[name]
    p=para();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=True
    pic=p.add_run().add_picture(str(SOURCE/'figures'/f'{name}.png'),width=Inches(10.15 if name in WIDE else 6.65))
    pic._inline.docPr.set('descr',title+'. '+description)
    p=para(f'Figure {number}  {title}. {description}',style='Caption');bookmark(p,f'fig_{number}',100+number)
    p.paragraph_format.keep_with_next=False;figures_added.append(name)

def figure_group(names):
    landscape=False
    for name in names:
        wide=name in WIDE
        if wide and not landscape:
            section(True);landscape=True
        elif wide and landscape:
            doc.add_page_break()
        elif not wide and landscape:
            section(False);landscape=False
        figure(name)
    if landscape:section(False)

def setup():
    s=doc.sections[0];s.page_width=Inches(8.27);s.page_height=Inches(11.69);s.top_margin=s.bottom_margin=Inches(.65);s.left_margin=s.right_margin=Inches(.6);s.header_distance=s.footer_distance=Inches(.28)
    s.different_first_page_header_footer=True
    for style in doc.styles:
        for border in style.element.findall('.//' + qn('w:pBdr')):
            border.getparent().remove(border)
        if style.type==1:
            style.font.name='Calibri';style.font.color.rgb=RGBColor(0,0,0)
    for name,size in [('Normal',10.5),('Title',25),('Subtitle',12),('Heading 1',16),('Heading 2',11.5),('Caption',9)]:
        st=doc.styles[name];st.font.size=Pt(size);st.font.color.rgb=RGBColor(0,0,0)
    doc.styles['Normal'].paragraph_format.space_after=Pt(7);doc.styles['Normal'].paragraph_format.line_spacing=1.12
    for name in ('Heading 1','Heading 2'):
        doc.styles[name].paragraph_format.space_before=Pt(14);doc.styles[name].paragraph_format.space_after=Pt(7);doc.styles[name].paragraph_format.keep_with_next=True
    doc.styles['Caption'].font.italic=False;doc.styles['Caption'].paragraph_format.space_after=Pt(10)
    h=s.header.paragraphs[0];h.text='JointSLA v2 Experimental Report';h.runs[0].font.size=Pt(8)
    f=s.footer.paragraphs[0];f.alignment=WD_ALIGN_PARAGRAPH.RIGHT;field(f,'PAGE','1')
    doc.core_properties.title='JointSLA v2 Experimental Report';doc.core_properties.subject='Frozen held-out experimental validation';doc.core_properties.author='';doc.core_properties.keywords='JointSLA, SLA, edge placement, held-out validation'
    update=OxmlElement('w:updateFields');update.set(qn('w:val'),'true');doc.settings.element.append(update)
    doc.settings.element.append(OxmlElement('w:doNotAutoCompressPictures'))

setup();current_title='Experiment overview'
para('Οργανωμένη αναφορά πειραμάτων JointSLA v2','Title')
para('Hardware grounded validation with held out seeds','Subtitle')
para('7 Οκτωβρίου 2026')
para('Σύνοψη αποτελέσματος').runs[0].bold=True
para('Το JointSLA-v2 βελτιώνει σημαντικά τα Gold SLA breaches έναντι του v1, αλλά δεν ικανοποιεί το συνολικό κριτήριο επιτυχίας. Διατηρεί σημαντικό aggregate SLA penalty στα 1x, χρησιμοποιεί σχεδόν τους πόρους του SLA-aware και χάνει το πλεονέκτημα latency στα 2x. Οι H1, H2, H5 και H6 περνούν. Οι H3 και H4 αποτυγχάνουν. Η αλγοριθμική φάση ολοκληρώνεται χωρίς v3 ή νέο tuning.')
table(['Πεδίο','Πρωτόκολλο'],[['Σενάριο','10 nodes, 40 services, 100 slots, 100 ms ανά slot'],['Development','Seeds 101–105, loads 0.5x / 1x / 2x, μία διαμόρφωση, 45 simulations'],['Held out','Seeds 31–60, loads 1x / 2x, 180 paired simulations'],['Επαλήθευση','244 tests, 3,046,965 held-out request outcomes, 40 paired tests'],['Figures','15 original figures with numbered captions'],['Freeze UTC','2026-10-07 15:59:44'],['Config SHA256',json.loads((SOURCE/'freeze_manifest.json').read_text())['config_sha256']]])
para('Η τεχνική αναφορά ακολουθεί στα αγγλικά. Τα ποσοστά των τεχνικών πινάκων δίνονται ως fractions, εκτός αν επισημαίνονται με %. Τα latency quantiles υπολογίζονται ανά run και μετά συνοψίζονται ανά seed. Περιλαμβάνονται τα θετικά και τα αρνητικά αποτελέσματα, το κόστος πόρων και οι περιορισμοί των συμπερασμάτων.')
doc.add_page_break();para('Contents','Title');field(doc.add_paragraph(),'TOC \\o "1-1" \\h \\z \\u','Contents will be updated by Word.')
doc.add_page_break();para('Figure index','Title')
for i,(name,title,caption) in enumerate(FIGS,1):
    p=para(f'Figure {i}  {title}  ');field(p,f'PAGEREF fig_{i} \\h','')
doc.add_page_break()
source=(SOURCE/'report.md').read_text(encoding='utf-8')
parts=re.split(r'^# (.+)$',source,flags=re.M)
assert len(parts[1::2])==27
titles={'1.0x Hardware-Grounded Results':'Hardware Grounded Results at 1x Load','2.0x High-Pressure Results':'High Pressure Results at 2x Load','Causality / No-Future Information':'Causality and Information Boundaries','Gold / Silver / Bronze':'Gold Silver and Bronze Results','Mean / p95 / p99':'Mean and Tail Latency','V2-H1 to V2-H6':'V2 Hypotheses H1 to H6','Performance-Resource Frontier':'Performance and Resource Frontier','Final B-Level Assessment':'Final Assessment for a B Level Paper'}
section_names=[]
for section_number,(original,body) in enumerate(zip(parts[1::2],parts[2::2]),1):
    current_title=titles.get(original,original.replace('-',' ').replace('/',' and '))
    h=heading(f'{section_number} {current_title}');bookmark(h,f'section_{section_number}',section_number);section_names.append(original)
    if original=='Final B-Level Assessment':h.paragraph_format.page_break_before=True
    lines=body.strip().splitlines();i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        if line.startswith('|'):
            block=[]
            while i<len(lines) and lines[i].startswith('|'):block.append(lines[i]);i+=1
            source_table(block);continue
        if line.startswith('```'):
            i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                p=para(lines[i]);p.paragraph_format.space_after=Pt(3)
                for r in p.runs:r.font.name='Consolas';r.font.size=Pt(8.5)
                i+=1
            i+=1;continue
        if line.strip()=='{':
            block=[]
            while i<len(lines):
                block.append(lines[i]);i+=1
                try:value=json.loads('\n'.join(block));break
                except json.JSONDecodeError:pass
            json_table(value);continue
        text=[]
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('|','```')):
            text.append(lines[i]);i+=1
        text=' '.join(text)
        if text.startswith('Independent receipt: '):
            para('Independent validation record').paragraph_format.keep_with_next=True;json_table(json.loads(text.split(': ',1)[1]));continue
        if original=='Recovery-Aware Headroom':
            para('For backlog q requests, observed arrival rate λ requests per second, class readiness R seconds, causal estimated serial cycle L seconds, deadline D seconds and slack h = max(D − L, 0), the bounded warm requirement is:')
            equation()
            para(text[text.index('Empty history'):]);continue
        if text.startswith('To regenerate the same frozen simulations'):
            text=text.replace('guards or erase previous validation history','guards; --force replaces v2 run outputs and preserves the generation ledger')
        para(text)
    figure_group(INSERT.get(original,[]))
assert set(figures_added)==set(FIG_INDEX) and len(figures_added)==15
doc.save(TARGET)
manifest=dict(source_report=str(SOURCE/'report.md'),source_report_sha256=sha(SOURCE/'report.md'),document=str(TARGET),source_sections=section_names,
    figures=[dict(number=i,title=title,source=str(SOURCE/'figures'/f'{name}.png'),sha256=sha(SOURCE/'figures'/f'{name}.png')) for i,(name,title,caption) in enumerate(FIGS,1)],
    tables=table_count,scope='Complete JointSLA-v2 report and all 15 original figures',language='Greek executive summary; English complete technical report',
    report_wording_correction='Force replaces v2 outputs while preserving the generation ledger; no frozen sources or numerical results modified.')
(OUT/'build_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(dict(document=str(TARGET),figures=len(figures_added),tables=table_count,technical_sections=len(section_names)),ensure_ascii=False))
