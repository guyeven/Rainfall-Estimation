from pathlib import Path
import json, csv
import numpy as np
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader, PdfWriter
ROOT=Path('/Users/isoto/Projects/Rainfall-Estimation')
# Execute only the table-data portion of the report generator.
s=(ROOT/'tmp/build_june_report.py').read_text()
ns={}; exec(s[:s.index("story += [tab(d,")],ns)
d=ns['d']; print(json.dumps(d[-3:],indent=2))
out=ROOT/'output/pdf/june2023_report_corrected.pdf'
styles=getSampleStyleSheet()
header=['Solver','N','RMSE<br/>mean','RMSE<br/>min','RMSE<br/>max','Bias<br/>mean','Bias<br/>min','Bias<br/>max','Pearson<br/>mean','Pearson<br/>min','Pearson<br/>max']
from reportlab.lib.styles import ParagraphStyle
hs=ParagraphStyle('Header',fontName='Helvetica-Bold',fontSize=6.5,leading=8,textColor=colors.white)
cs=ParagraphStyle('Cell',fontSize=7,leading=9)
rows=[[Paragraph(x,hs) for x in header]]+[[Paragraph(str(x),cs) for x in r] for r in d[1:]]
t=Table(rows,colWidths=[139,23]+[41]*9,repeatRows=1)
t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#172033')),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#CBD5E1')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F8FAFC')]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),3)]))
page=ROOT/'tmp/pdfs/june_corrected_summary.pdf'
SimpleDocTemplate(str(page),pagesize=A4,leftMargin=32,rightMargin=32,topMargin=40,bottomMargin=40).build([Paragraph('1. Summary metrics',styles['Heading1']),t,Spacer(1,12),Paragraph('Each row summarizes 100 patches. Mean/min/max are calculated separately across the per-patch RMSE, signed bias (prediction minus ground truth), and Pearson correlation. RMSE and bias are in mm/h. Only finite paired pixels are used; undefined correlations are excluded.',styles['BodyText'])])
r=PdfReader('/Users/isoto/Downloads/june2023_report2.pdf'); w=PdfWriter()
for i,p in enumerate(r.pages): w.add_page(PdfReader(str(page)).pages[0] if i==1 else p)
with out.open('wb') as f:w.write(f)
with (ROOT/'output/pdf/june2023_summary_corrected.csv').open('w') as f:
 wr=csv.writer(f);wr.writerows(d)
import pdfplumber
with pdfplumber.open(out) as pdf:
 assert len(pdf.pages)==len(r.pages)
 pdf.pages[1].to_image(resolution=140).save('/tmp/june_corrected.png')
 print(pdf.pages[1].extract_text())
